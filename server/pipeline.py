"""The interpreter pipeline: (audio ->) text -> translation -> speech -> other device.

    speaker device                     server                         listener device
    --------------                     ------                         ---------------
    browser STT text  --final-->  loop guard -> translate -> split -> TTS --audio/speak-->  playback queue
    or PCM frames     --binary--> VAD -> Azure STT ---^

Work items for one speaker are processed strictly in order by that device's
worker task, so sentences never arrive shuffled. An interrupt bumps
`session.generation`; anything produced for an older generation is dropped.
"""
from __future__ import annotations

import asyncio
import base64
import logging

from .config import LANGUAGES, ROLE_LANG, Settings
from .http_util import ProviderError
from .latency import UtteranceTiming
from .sentences import split_sentences
from .session import Device, Session, other_role
from .stt import STT
from .translate import ChainTranslator
from .tts import ChainTTS

log = logging.getLogger("interpreter.pipeline")


class Pipeline:
    def __init__(self, settings: Settings, translator: ChainTranslator, tts: ChainTTS, server_stt: STT | None):
        self.settings = settings
        self.translator = translator
        self.tts = tts
        self.server_stt = server_stt

    # ------------------------------------------------------------ workers
    def ensure_worker(self, session: Session, device: Device) -> None:
        if device.worker is None or device.worker.done():
            device.worker = asyncio.create_task(self._worker(session, device))

    async def _worker(self, session: Session, device: Device) -> None:
        while not device.closed:
            kind, payload, timing = await device.queue.get()
            try:
                if kind == "audio":
                    await self.process_audio(session, device, payload, timing)
                else:
                    await self.process_text(session, device, payload, timing)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # never let one bad utterance kill the worker
                log.exception("pipeline error")
                await device.send({"type": "error", "where": "pipeline", "message": f"{type(e).__name__}: {e}"})

    def submit_text(self, session: Session, device: Device, text: str) -> None:
        self.ensure_worker(session, device)
        device.queue.put_nowait(("text", text, UtteranceTiming()))

    def submit_audio(self, session: Session, device: Device, pcm: bytes) -> None:
        self.ensure_worker(session, device)
        device.queue.put_nowait(("audio", pcm, UtteranceTiming()))

    # ------------------------------------------------------------ stages
    async def process_audio(self, session: Session, device: Device, pcm: bytes, timing: UtteranceTiming) -> None:
        if self.server_stt is None:
            await device.send({"type": "error", "where": "stt",
                               "message": "Server speech recognition is not configured (no AZURE_SPEECH_KEY). "
                                          "Switch to Browser recognition."})
            return
        await session.broadcast({"type": "status", "role": device.role, "state": "recognizing"})
        try:
            text = await self.server_stt.transcribe(pcm, device.lang)
        except ProviderError as e:
            await session.broadcast({"type": "status", "role": device.role, "state": "idle"})
            await device.send({"type": "error", "where": "stt", "provider": e.provider,
                               "status": e.status, "message": e.message})
            return
        timing.mark("stt_done")
        if not text:
            await session.broadcast({"type": "status", "role": device.role, "state": "idle"})
            return
        await self.process_text(session, device, text, timing)

    async def process_text(self, session: Session, device: Device, text: str, timing: UtteranceTiming) -> None:
        text = text.strip()
        if not text:
            return
        guard = session.loopguard
        reason = guard.echo_reason(text)
        if reason:
            await device.send({"type": "dropped", "role": device.role, "text": text, "reason": reason})
            return

        src = device.lang
        listener_now = session.peer_of(device.role)
        dst = listener_now.lang if listener_now else ROLE_LANG[other_role(device.role)]
        direction = f"{device.role}->{other_role(device.role)}"
        uid = session.next_utterance_id(device.role)
        generation = session.generation
        await session.broadcast({"type": "transcript", "id": uid, "role": device.role, "lang": src,
                                 "final": True, "text": text})

        timing.mark("translate_start")
        if src == dst:  # both people chose the same language: nothing to translate
            translated, provider = text, "same language"
        else:
            try:
                translated = await self.translator.translate(text, src, dst)
            except ProviderError as e:
                await session.broadcast({"type": "error", "where": "translate", "id": uid, "message": e.message})
                await session.broadcast({"type": "status", "role": device.role, "state": "idle"})
                return
            provider = self.translator.last_provider
        timing.mark("translate_done")
        await session.broadcast({"type": "translation", "id": uid, "role": device.role, "lang": dst,
                                 "text": translated, "provider": provider})

        listener = session.peer_of(device.role)
        if listener is None:
            await device.send({"type": "notice", "id": uid,
                               "message": "The other device is not connected - translation shown but not played."})
            timing.mark("done")
            await session.broadcast({"type": "status", "role": device.role, "state": "idle"})
            return

        guard.remember_played(translated)
        await self._speak(session, listener, uid, translated, dst, generation, timing)
        timing.mark("done")
        summary = timing.summary()
        session.latency[direction].add(summary["first_audio_ms"])
        await session.broadcast({"type": "latency", "id": uid, "direction": direction, "from_role": device.role,
                                 "src_lang": src, "dst_lang": dst, **summary,
                                 "stats": session.latency[direction].snapshot()})
        await session.broadcast({"type": "status", "role": device.role, "state": "idle"})

    async def _speak(self, session: Session, listener: Device, uid: str, text: str, lang: str,
                     generation: int, timing: UtteranceTiming) -> None:
        chunks = split_sentences(text) or [text]
        # synthesise sentences concurrently (max 3 in flight), deliver strictly in order
        sem = asyncio.Semaphore(3)

        async def synth(chunk: str):
            async with sem:
                return await self.tts.synthesize(chunk, lang)

        tasks = [asyncio.create_task(synth(c)) for c in chunks]
        try:
            for seq, (chunk, task) in enumerate(zip(chunks, tasks)):
                result = await task
                if session.generation != generation or listener.closed:
                    return  # interrupted
                last = seq == len(chunks) - 1
                if result.audio is not None:
                    msg = {"type": "audio", "id": uid, "seq": seq, "last": last, "lang": lang, "text": chunk,
                           "mime": result.mime, "provider": result.provider,
                           "data": base64.b64encode(result.audio).decode("ascii")}
                else:
                    msg = {"type": "speak", "id": uid, "seq": seq, "last": last, "lang": lang,
                           "bcp47": LANGUAGES[lang]["bcp47"], "text": chunk, "provider": "browser"}
                if seq == 0:
                    timing.mark("first_audio")
                    if self.tts.last_errors:
                        await session.broadcast({"type": "notice", "id": uid,
                                                 "message": "Cloud voice failed, using the device's built-in voice: "
                                                            + self.tts.last_errors[-1][:200]})
                await listener.send(msg)
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()
