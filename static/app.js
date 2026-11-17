/* Multilingual voice interpreter client (English / Telugu / Tamil / Hindi; two seats: "laptop" + "phone").
 *
 * Recognition modes
 *   browser : Web Speech API (Chrome/Edge) recognises speech on the device (free, live partial text)
 *   server  : 16 kHz PCM streamed to the server -> VAD -> Azure Speech
 * Playback
 *   "audio" messages (mp3/wav from Azure)  -> Web Audio
 *   "speak" messages (no cloud voice)       -> speechSynthesis on this device
 * Feedback-loop guard: while anything plays (here or on the other device) recognition is paused.
 */
(() => {
  'use strict';

  const $ = (s) => document.querySelector(s);
  const params = new URLSearchParams(location.search);
  const isAndroid = /Android/i.test(navigator.userAgent);
  const isMobile = /Android|iPhone|iPad|Mobile/i.test(navigator.userAgent);
  const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
  const LANG = {
    en: { name: 'English', native: 'English', bcp47: 'en-IN', test: 'Hello, this is a test.' },
    te: { name: 'Telugu', native: 'తెలుగు', bcp47: 'te-IN', test: 'నమస్కారం, ఇది పరీక్ష.' },
    ta: { name: 'Tamil', native: 'தமிழ்', bcp47: 'ta-IN', test: 'வணக்கம், இது ஒரு சோதனை.' },
    hi: { name: 'Hindi', native: 'हिन्दी', bcp47: 'hi-IN', test: 'नमस्ते, यह एक परीक्षण है।' },
  };
  const ROLE_DEFAULT_LANG = { laptop: 'en', phone: 'te' };
  function safeGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function safeSet(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }

  const S = {
    role: null, session: null, lang: null, peerLang: null,
    ws: null, wsOpen: false, reconnectDelay: 500, closedByUser: false,
    config: null, hello: null,
    sttMode: 'browser', serverSttAvailable: false,
    micOn: false, gateClosed: false, localPlaying: false,
    audioCtx: null, recognizer: null, streamer: null,
    bubbles: new Map(), partialBubble: { laptop: null, phone: null },
    lastRtt: null,
  };
  window.__interp = S; // for debugging / automated tests

  // ------------------------------------------------------------------ utils
  function log(...a) { console.log('[interp]', ...a); }
  function fmtMs(v) { if (v == null) return '–'; if (v < 1) return '<1 ms'; return v >= 1000 ? (v / 1000).toFixed(2) + ' s' : Math.round(v) + ' ms'; }
  function el(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }

  function notice(msg, kind = 'info', ttl = 9000, key = null) {
    const box = $('#notices');
    if (key) { const old = box.querySelector(`[data-key="${key}"]`); if (old) old.remove(); }
    const b = el('div', `banner ${kind}`);
    if (key) b.dataset.key = key;
    b.append(el('span', null, msg));
    const x = el('button', null, '✕'); x.onclick = () => b.remove(); b.append(x);
    box.prepend(b);
    while (box.children.length > 3) box.lastChild.remove();
    if (ttl) setTimeout(() => b.remove(), ttl);
  }

  function send(obj) {
    if (S.ws && S.ws.readyState === 1) { S.ws.send(JSON.stringify(obj)); return true; }
    return false;
  }

  // ------------------------------------------------------------------ audio unlock
  function ensureAudioCtx() {
    if (!S.audioCtx) {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      S.audioCtx = new Ctx();
    }
    if (S.audioCtx.state === 'suspended') S.audioCtx.resume();
    return S.audioCtx;
  }
  function unlockAudio() {
    try {
      const ctx = ensureAudioCtx();
      const b = ctx.createBuffer(1, 1, 22050); const src = ctx.createBufferSource();
      src.buffer = b; src.connect(ctx.destination); src.start(0);
    } catch (e) { log('audio unlock failed', e); }
    try { if ('speechSynthesis' in window) { const u = new SpeechSynthesisUtterance(' '); u.volume = 0; speechSynthesis.speak(u); } } catch (e) {}
  }

  // ------------------------------------------------------------------ voices
  let voices = [];
  function loadVoices() { if ('speechSynthesis' in window) voices = speechSynthesis.getVoices() || []; updateVoiceInfo(); }
  if ('speechSynthesis' in window) { loadVoices(); speechSynthesis.onvoiceschanged = loadVoices; }
  function pickVoice(lang) {
    const want = LANG[lang].bcp47.toLowerCase();
    const prefix = lang.toLowerCase();
    return voices.find(v => v.lang && v.lang.toLowerCase().replace('_', '-') === want)
      || voices.find(v => v.lang && v.lang.toLowerCase().startsWith(prefix)) || null;
  }
  function updateVoiceInfo() {
    if (!S.lang) return;
    const v = pickVoice(S.lang);
    const cloud = S.hello && S.hello.tts_chain && S.hello.tts_chain[0] !== 'browser';
    let txt = cloud ? `Cloud voice (${S.hello.tts_chain[0]}) plays ${LANG[S.lang].name} here. ` : '';
    txt += v ? `Fallback device voice: ${v.name} (${v.lang}).`
      : `No ${LANG[S.lang].name} voice found on this device` + (S.lang !== 'en'
        ? ` — Android: Settings → Text-to-speech → Google → Install voice data → ${LANG[S.lang].name}.` : '.');
    const vi = $('#voiceInfo'); if (vi) vi.textContent = txt;
  }

  // ------------------------------------------------------------------ playback queue
  const Player = {
    queue: [], current: null, busy: false, generation: 0,
    enqueue(item) { this.queue.push(item); this.queue.sort((a, b) => a.order - b.order); this.pump(); },
    async pump() {
      if (this.busy) return;
      const item = this.queue.shift();
      if (!item) { this.setPlaying(false); return; }
      this.busy = true;
      this.setPlaying(true, item);
      const gen = this.generation;
      try {
        if (item.kind === 'audio') await this.playAudio(item);
        else await this.speak(item);
      } catch (e) {
        log('playback error', e);
        notice('Could not play audio: ' + (e && e.message || e), 'warn', 6000, 'play');
      }
      if (gen !== this.generation) return; // flushed meanwhile
      this.busy = false;
      this.current = null;
      this.pump();
    },
    playAudio(item) {
      return new Promise(async (resolve) => {
        const bytes = Uint8Array.from(atob(item.data), c => c.charCodeAt(0));
        const ctx = ensureAudioCtx();
        if (ctx.state !== 'running') {
          try { await Promise.race([ctx.resume(), new Promise(r => setTimeout(r, 300))]); } catch (e) {}
        }
        if (ctx.state !== 'running') notice('Tap anywhere on the screen to enable sound.', 'warn', 6000, 'tapsound');
        let buf;
        try { buf = await ctx.decodeAudioData(bytes.buffer.slice(0)); }
        catch (e) {
          // fallback: <audio> element
          const url = URL.createObjectURL(new Blob([bytes], { type: item.mime || 'audio/mpeg' }));
          const a = new Audio(url);
          this.current = { stop: () => { a.pause(); resolve(); } };
          a.onended = () => { URL.revokeObjectURL(url); resolve(); };
          a.onerror = () => { URL.revokeObjectURL(url); resolve(); };
          a.play().catch(() => resolve());
          return;
        }
        const src = ctx.createBufferSource();
        src.buffer = buf; src.connect(ctx.destination);
        let done = false; const finish = () => { if (!done) { done = true; resolve(); } };
        src.onended = finish;
        this.current = { stop: () => { try { src.stop(); } catch (e) {} finish(); } };
        src.start();
        setTimeout(finish, buf.duration * 1000 + 1500); // safety net
      });
    },
    speak(item) {
      return new Promise((resolve) => {
        if (!('speechSynthesis' in window)) { notice('This browser cannot speak text aloud.', 'warn', 6000, 'tts'); return resolve(); }
        const u = new SpeechSynthesisUtterance(item.text);
        u.lang = item.bcp47 || LANG[item.lang].bcp47;
        const v = pickVoice(item.lang); if (v) u.voice = v;
        u.rate = 1.0;
        let done = false; const finish = () => { if (!done) { done = true; clearTimeout(t); resolve(); } };
        u.onend = finish; u.onerror = finish;
        // Chrome sometimes never fires onend: estimate duration as a safety net
        const t = setTimeout(finish, 2500 + item.text.length * 110);
        this.current = { stop: () => { speechSynthesis.cancel(); finish(); } };
        speechSynthesis.speak(u);
      });
    },
    flush() {
      this.generation++;
      this.queue = [];
      if (this.current) this.current.stop();
      this.current = null; this.busy = false;
      try { if ('speechSynthesis' in window) speechSynthesis.cancel(); } catch (e) {}
      this.setPlaying(false);
    },
    setPlaying(on, item) {
      if (on !== S.localPlaying) {
        S.localPlaying = on;
        send({ type: 'playback', state: on ? 'start' : 'end' });
        applyPause();
      }
      const ps = $('#playStatus');
      ps.classList.toggle('active', on);
      $('#playText').textContent = on
        ? `Playing ${LANG[item.lang].name}${item.provider ? ' · ' + item.provider + ' voice' : ''}`
        : 'Ready';
    },
  };

  // ------------------------------------------------------------------ browser recognition
  class BrowserRecognizer {
    constructor(lang) {
      this.lang = lang; this.want = false; this.running = false; this.rec = null; this.lastFinalAt = 0;
      this.restartTimer = null; this.errorCount = 0;
    }
    static supported() { return !!SpeechRec; }
    build() {
      const r = new SpeechRec();
      r.lang = LANG[this.lang].bcp47;
      r.interimResults = true;
      r.maxAlternatives = 1;
      // Android Chrome duplicates results in continuous mode -> use single-shot and restart.
      r.continuous = !isAndroid;
      r.onstart = () => { this.running = true; this.errorCount = 0; setMicLabel(); };
      r.onresult = (ev) => {
        let interim = '';
        for (let i = ev.resultIndex; i < ev.results.length; i++) {
          const res = ev.results[i];
          const txt = res[0].transcript.trim();
          if (!txt) continue;
          if (res.isFinal) { this.lastFinalAt = performance.now(); onLocalFinal(txt); }
          else interim += (interim ? ' ' : '') + txt;
        }
        if (interim) onLocalPartial(interim);
      };
      r.onerror = (ev) => {
        log('recognition error', ev.error);
        if (ev.error === 'not-allowed' || ev.error === 'service-not-allowed') {
          this.want = false; setMic(false);
          notice('Microphone permission denied. Allow the microphone for this site (lock icon in the address bar) and try again.', 'bad', 0, 'perm');
        } else if (ev.error === 'network') {
          this.errorCount++;
          notice('Speech recognition needs internet (Google speech service). Check the connection' +
            (S.serverSttAvailable ? ' or switch to Azure recognition in Settings.' : '.'), 'warn', 8000, 'recnet');
        } else if (ev.error === 'language-not-supported') {
          this.want = false; setMic(false);
          notice(`This browser cannot recognise ${LANG[this.lang].name}. Use Chrome` +
            (S.serverSttAvailable ? ', or switch to Azure recognition in Settings.' : '.'), 'bad', 0, 'lang');
        }
        // 'no-speech' / 'aborted' are normal; onend restarts
      };
      r.onend = () => {
        this.running = false;
        if (this.want && !isPaused()) {
          const delay = this.errorCount > 2 ? 1500 : 150;
          clearTimeout(this.restartTimer);
          this.restartTimer = setTimeout(() => this.start(), delay);
        }
        setMicLabel();
      };
      return r;
    }
    start() {
      this.want = true;
      if (this.running || isPaused()) return;
      try { this.rec = this.build(); this.rec.start(); }
      catch (e) { log('rec start failed', e); }
    }
    pause() { clearTimeout(this.restartTimer); if (this.rec && this.running) { try { this.rec.abort(); } catch (e) {} } }
    resume() { if (this.want) this.start(); }
    stop() { this.want = false; this.pause(); clearPartial(S.role); }
  }

  // ------------------------------------------------------------------ server streaming
  class ServerStreamer {
    constructor() { this.stream = null; this.node = null; this.source = null; this.active = false; }
    async start() {
      const ctx = ensureAudioCtx();
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
      });
      await ctx.audioWorklet.addModule('/static/capture-worklet.js');
      this.source = ctx.createMediaStreamSource(this.stream);
      this.node = new AudioWorkletNode(ctx, 'capture-processor');
      const sink = ctx.createGain(); sink.gain.value = 0;
      this.source.connect(this.node); this.node.connect(sink); sink.connect(ctx.destination);
      this.node.port.onmessage = (ev) => {
        const { pcm, rms } = ev.data;
        showLevel(isPaused() ? 0 : rms);
        if (!isPaused() && S.ws && S.ws.readyState === 1) S.ws.send(pcm);
      };
      this.active = true;
    }
    pause() {} resume() {}
    stop() {
      this.active = false;
      try { this.node && this.node.disconnect(); } catch (e) {}
      try { this.source && this.source.disconnect(); } catch (e) {}
      if (this.stream) this.stream.getTracks().forEach(t => t.stop());
      this.stream = this.node = this.source = null; showLevel(0);
    }
  }

  function showLevel(rms) {
    const k = Math.min(1, rms / 4000);
    $('#micRing').style.transform = `scale(${1 + k * 0.35})`;
  }

  // ------------------------------------------------------------------ mic control
  function isPaused() { return S.localPlaying || S.gateClosed; }
  function applyPause() {
    const paused = isPaused();
    if (S.recognizer) paused ? S.recognizer.pause() : S.recognizer.resume();
    if (paused) clearPartial(S.role);
    setMicLabel();
  }
  function setMicLabel() {
    const btn = $('#micBtn'); const label = $('#micLabel');
    btn.classList.toggle('on', S.micOn && !isPaused());
    btn.classList.toggle('paused', S.micOn && isPaused());
    btn.setAttribute('aria-pressed', String(S.micOn));
    if (!S.micOn) label.textContent = 'Tap to talk';
    else if (S.localPlaying) label.textContent = 'Paused · playing translation';
    else if (S.gateClosed) label.textContent = 'Paused · other device playing';
    else label.textContent = `Listening · ${LANG[S.lang].name}`;
  }

  async function setMic(on) {
    if (on === S.micOn) return;
    if (on) {
      unlockAudio();
      if (!window.isSecureContext) { notice('Microphone needs HTTPS (or localhost). See the address tip on the start screen.', 'bad', 0, 'perm'); return; }
      S.micOn = true;
      try {
        if (S.sttMode === 'browser') {
          if (!BrowserRecognizer.supported()) throw new Error('This browser has no built-in speech recognition. Use Chrome' + (S.serverSttAvailable ? ' or switch to Azure recognition in Settings.' : '.'));
          S.recognizer = new BrowserRecognizer(S.lang);
          S.recognizer.start();
        } else {
          S.streamer = new ServerStreamer();
          await S.streamer.start();
        }
      } catch (e) {
        S.micOn = false;
        stopEngines();
        notice(e.name === 'NotAllowedError' ? 'Microphone permission denied. Allow it via the lock icon in the address bar.' : (e.message || String(e)), 'bad', 0, 'perm');
      }
    } else {
      S.micOn = false;
      stopEngines();
    }
    send({ type: 'mic', on: S.micOn });
    setMicLabel();
  }
  function stopEngines() {
    if (S.recognizer) { S.recognizer.stop(); S.recognizer = null; }
    if (S.streamer) { S.streamer.stop(); S.streamer = null; }
  }

  function onLocalPartial(text) { if (!isPaused()) send({ type: 'partial', text }); }
  function onLocalFinal(text) { if (!isPaused()) send({ type: 'final', text }); }

  // ------------------------------------------------------------------ conversation rendering
  function hideEmpty() { const e = $('#emptyState'); if (e) e.remove(); }
  function scrollDown() { const c = $('#conversation'); c.scrollTop = c.scrollHeight; }
  function makeBubble(role) {
    hideEmpty();
    const b = el('div', `bubble from-${role} ${role === S.role ? 'mine' : 'theirs'}`);
    const who = el('div', 'who');
    who.append(el('span', null, (role === 'laptop' ? '💻 Laptop' : '📱 Phone') + (role === S.role ? ' (you)' : '')));
    b.append(who);
    const orig = el('div', 'orig'); b.append(orig);
    const trans = el('div', 'trans'); trans.append(el('span', 'pending', 'translating…')); b.append(trans);
    const meta = el('div', 'meta'); b.append(meta);
    $('#conversation').append(b);
    return b;
  }
  function setLangText(node, lang, text) {
    node.textContent = '';
    node.append(el('span', `lbl ${lang}`, lang.toUpperCase()));
    const t = el('span', null, text); t.lang = lang; node.append(t);
  }
  function clearPartial(role) {
    const p = S.partialBubble[role]; if (p) { p.remove(); S.partialBubble[role] = null; }
  }
  function onTranscript(m) {
    if (!m.final) {
      let p = S.partialBubble[m.role];
      if (!p) { p = makeBubble(m.role); p.classList.add('partial'); p.querySelector('.trans').remove(); S.partialBubble[m.role] = p; }
      setLangText(p.querySelector('.orig'), m.lang, m.text);
      $('#conversation').append(p); scrollDown();
      return;
    }
    clearPartial(m.role);
    const b = makeBubble(m.role);
    setLangText(b.querySelector('.orig'), m.lang, m.text);
    S.bubbles.set(m.id, b);
    scrollDown();
  }
  function onTranslation(m) {
    const b = S.bubbles.get(m.id); if (!b) return;
    setLangText(b.querySelector('.trans'), m.lang, m.text);
    b.querySelector('.meta').textContent = `translated by ${m.provider || '?'}`;
    scrollDown();
  }
  function onLatency(m) {
    const b = S.bubbles.get(m.id);
    if (b) {
      const parts = [];
      if (m.stt_ms) parts.push(`STT ${fmtMs(m.stt_ms)}`);
      parts.push(`translate ${fmtMs(m.translate_ms)}`, `voice ${fmtMs(m.tts_first_ms)}`, `first audio ${fmtMs(m.first_audio_ms)}`);
      b.querySelector('.meta').textContent += ' · ' + parts.join(' · ');
    }
    $('#latStt').textContent = m.stt_ms ? fmtMs(m.stt_ms) : (S.sttMode === 'browser' ? 'on-device' : '–');
    $('#latMt').textContent = fmtMs(m.translate_ms);
    $('#latTts').textContent = fmtMs(m.tts_first_ms);
    $('#latFirst').textContent = fmtMs(m.first_audio_ms);
    const med = m.stats && m.stats.median_ms;
    if (m.direction === 'phone->laptop') $('#latMedP2L').textContent = fmtMs(med);
    else if (m.direction === 'laptop->phone') $('#latMedL2P').textContent = fmtMs(med);
  }

  // ------------------------------------------------------------------ device cards
  function renderState(m) {
    for (const role of ['laptop', 'phone']) {
      const card = $('#dev-' + role); const d = m.devices[role];
      card.classList.toggle('online', !!d);
      card.classList.toggle('me', role === S.role);
      card.querySelector('.you-tag').classList.toggle('hidden', role !== S.role);
      if (!card.dataset.activity) card.querySelector('.state').textContent = d ? 'online' : 'offline';
      card.querySelector('.mic').textContent = d ? (d.mic_on ? `mic on · ${d.stt_mode === 'server' ? 'Azure' : 'browser'} STT` : 'mic off') : 'not joined';
      card.querySelector('.rtt').textContent = d && d.rtt_ms != null ? `${Math.round(d.rtt_ms)} ms` : '– ms';
      const chip = card.querySelector('.card-lang');
      const lang = d ? d.lang : null;
      chip.className = 'lang-chip card-lang' + (lang ? ' ' + lang : '');
      chip.textContent = lang ? (LANG[lang] ? LANG[lang].native : lang) : '—';
      if (lang) chip.lang = lang;
      if (role === S.role && d && d.lang !== S.lang) S.lang = d.lang;
      if (role !== S.role) S.peerLang = d ? d.lang : null;
    }
    const peer = S.role === 'laptop' ? 'phone' : 'laptop';
    const peerOnline = !!m.devices[peer];
    if (S.role === 'laptop') $('#pairPanel').classList.toggle('hidden', peerOnline);
    if (m.latency) {
      const p2l = m.latency['phone->laptop'], l2p = m.latency['laptop->phone'];
      if (p2l && p2l.median_ms) $('#latMedP2L').textContent = fmtMs(p2l.median_ms);
      if (l2p && l2p.median_ms) $('#latMedL2P').textContent = fmtMs(l2p.median_ms);
    }
  }
  function setActivity(role, state) {
    const card = $('#dev-' + role); if (!card) return;
    card.classList.toggle('speaking', state === 'speaking' || state === 'recognizing' || state === 'translating');
    card.classList.toggle('playing', state === 'playing');
    const labels = { speaking: 'speaking…', recognizing: 'recognising…', translating: 'translating…', playing: 'playing translation', idle: 'online' };
    card.dataset.activity = state === 'idle' ? '' : state;
    if (card.classList.contains('online')) card.querySelector('.state').textContent = labels[state] || state;
  }

  // ------------------------------------------------------------------ websocket
  function setConn(kind, text) {
    const b = $('#connBadge'); b.className = 'conn ' + kind; $('#connText').textContent = text;
  }
  function connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const url = `${proto}://${location.host}/ws?session=${encodeURIComponent(S.session)}&role=${S.role}&stt_mode=${S.sttMode}&lang=${S.lang}`;
    setConn('wait', 'Connecting…');
    const ws = new WebSocket(url);
    S.ws = ws;
    ws.onopen = () => {
      S.wsOpen = true; S.reconnectDelay = 500; setConn('ok', 'Connected');
      if (S.micOn) send({ type: 'mic', on: true });
      ping();
    };
    ws.onmessage = (ev) => { try { handle(JSON.parse(ev.data)); } catch (e) { log('bad message', e); } };
    ws.onclose = () => {
      S.wsOpen = false;
      if (S.closedByUser) { setConn('bad', 'Left'); return; }
      setConn('bad', 'Reconnecting…');
      setTimeout(() => { if (!S.closedByUser) connect(); }, S.reconnectDelay);
      S.reconnectDelay = Math.min(S.reconnectDelay * 2, 5000);
    };
    ws.onerror = () => {};
  }
  function ping() { send({ type: 'ping', t: performance.now() }); }
  setInterval(() => { if (S.wsOpen) ping(); }, 5000);

  function handle(m) {
    switch (m.type) {
      case 'hello':
        S.hello = m; S.lang = m.lang; S.peerLang = m.peer_lang; S.serverSttAvailable = m.server_stt_available;
        $('#langSelectCall').value = m.lang;
        S.sttMode = m.stt_mode;
        if (S.sttMode === 'browser' && !BrowserRecognizer.supported() && S.serverSttAvailable) {
          S.sttMode = 'server'; send({ type: 'mode', stt_mode: 'server' });
          notice('This browser has no built-in speech recognition — using Azure recognition on the server.', 'info');
        }
        if (S.sttMode === 'browser' && !BrowserRecognizer.supported()) {
          notice('This browser cannot do speech recognition. Please open this page in Google Chrome.', 'bad', 0, 'nosr');
        }
        $('#providerInfo').textContent = `Translation: ${m.translate_chain.join(' → ')} · Voice: ${m.tts_chain.join(' → ')}`;
        updateModeUI(); updateVoiceInfo();
        break;
      case 'state': renderState(m); break;
      case 'status': setActivity(m.role, m.state); break;
      case 'gate': S.gateClosed = !!m.closed; applyPause(); break;
      case 'transcript': onTranscript(m); break;
      case 'translation': onTranslation(m); break;
      case 'audio':
        Player.enqueue({ kind: 'audio', order: orderOf(m), id: m.id, seq: m.seq, data: m.data, mime: m.mime, lang: m.lang, provider: m.provider });
        break;
      case 'speak':
        Player.enqueue({ kind: 'speak', order: orderOf(m), id: m.id, seq: m.seq, text: m.text, lang: m.lang, bcp47: m.bcp47, provider: 'device' });
        break;
      case 'latency': onLatency(m); break;
      case 'flush':
        Player.flush(); S.gateClosed = false; applyPause();
        if (m.by !== S.role) notice('Playback stopped by the other device.', 'info', 3000, 'flush');
        break;
      case 'dropped': {
        clearPartial(m.role);
        notice(`Ignored “${m.text.slice(0, 60)}” — ${m.reason}.`, 'info', 4000, 'drop');
        break;
      }
      case 'notice': notice(m.message, 'info', 7000, 'n-' + (m.message || '').slice(0, 20)); break;
      case 'error':
        notice(`${m.where ? m.where.toUpperCase() + ': ' : ''}${m.message}`, 'bad', 12000, 'err-' + m.where);
        if (m.where === 'stt' && S.sttMode === 'server' && BrowserRecognizer.supported()) {
          notice('Switching to browser recognition.', 'info', 5000);
          switchMode('browser');
        }
        break;
      case 'pong': {
        const rtt = performance.now() - m.t; S.lastRtt = rtt; send({ type: 'rtt', ms: rtt });
        break;
      }
      case 'kicked':
        S.closedByUser = true; setMic(false); notice(m.message + ' This tab is disconnected.', 'bad', 0); setConn('bad', 'Replaced');
        break;
    }
  }
  let orderCounter = 0; const orderBase = new Map();
  function orderOf(m) {
    if (!orderBase.has(m.id)) orderBase.set(m.id, (++orderCounter) * 1000);
    return orderBase.get(m.id) + m.seq;
  }

  // ------------------------------------------------------------------ settings
  function updateModeUI() {
    document.querySelectorAll('#modeSeg button').forEach(b => {
      b.classList.toggle('active', b.dataset.mode === S.sttMode);
      if (b.dataset.mode === 'server') b.disabled = !S.serverSttAvailable;
      if (b.dataset.mode === 'browser') b.disabled = !BrowserRecognizer.supported();
    });
    $('#modeHelp').textContent = S.sttMode === 'browser'
      ? 'Chrome recognises speech on this device (free, live text while you speak). Needs internet.'
      : 'Microphone audio is streamed to the server and recognised by Azure Speech (free tier: 5 h/month).';
    if (!S.serverSttAvailable) $('#modeHelp').textContent += ' Azure recognition is unavailable: no AZURE_SPEECH_KEY on the server.';
  }
  async function switchMode(mode) {
    if (mode === S.sttMode) return;
    const wasOn = S.micOn;
    if (wasOn) await setMic(false);
    S.sttMode = mode; send({ type: 'mode', stt_mode: mode }); updateModeUI();
    if (wasOn) await setMic(true);
  }

  async function runSelftest() {
    const out = $('#selftestOut'); out.classList.remove('hidden'); out.textContent = 'Calling the real services… (5–20 s)';
    try {
      const r = await (await fetch('/api/selftest')).json();
      const lines = [];
      for (const t of r.translation) lines.push(`${t.ok ? '✅' : '❌'} ${t.check} [${t.provider}] ${t.ms} ms ${t.ok ? '→ ' + t.output : '— ' + t.error}`);
      for (const t of r.speech) lines.push(`${t.ok ? '✅' : '❌'} ${t.check} ${t.ms} ms ${t.ok ? '→ ' + (t.output || '') : '— ' + t.error}`);
      if (r.azure_translator_diagnosis) {
        lines.push('', 'Azure Translator region diagnosis:');
        for (const d of r.azure_translator_diagnosis) lines.push(`${d.ok ? '✅' : d.ok === false ? '❌' : 'ℹ️'} ${d.variant}${d.region_header ? ' (' + d.region_header + ')' : ''} ${d.ok ? '→ works! set AZURE_TRANSLATOR_REGION=' + (d.region_header || '(empty)') : '— ' + (d.error || '')}`);
      }
      out.textContent = lines.join('\n');
    } catch (e) { out.textContent = 'Self-test failed: ' + e; }
  }

  // ------------------------------------------------------------------ pairing (laptop)
  async function showPairing() {
    if (S.role !== 'laptop') return;
    const urls = [];
    const cfg = S.config;
    const host = location.hostname;
    const isLocalHost = host === 'localhost' || host === '127.0.0.1';
    const isBareIp = /^\d{1,3}(\.\d{1,3}){3}$/.test(host);
    // A real public domain (deployed to a host like Render/Railway/Fly) already has
    // valid HTTPS on this very page, so the page's own address IS the link to share
    // - no self-signed certificate and no same-Wi-Fi requirement.
    if (!isLocalHost && !isBareIp) {
      urls.push(`${location.origin}/?session=${S.session}&role=phone`);
    }
    const ips = (cfg && cfg.lan_ips) || [];
    for (const ip of ips) urls.push(`https://${ip}:${cfg.https_port}/?session=${S.session}&role=phone`);
    const box = $('#phoneUrls'); box.textContent = '';
    if (!urls.length) box.append(el('span', 'muted', 'No network address found — is the laptop on Wi-Fi?'));
    for (const u of urls) { const a = el('a', null, u); a.href = u; a.target = '_blank'; box.append(a); }
    const qr = $('#qr'); qr.textContent = '';
    if (urls.length && window.QRCode) new QRCode(qr, { text: urls[0], width: 132, height: 132, correctLevel: QRCode.CorrectLevel.M });
    $('#pairPanel').classList.remove('hidden');
  }

  // ------------------------------------------------------------------ join flow
  async function loadConfig() {
    try { S.config = await (await fetch('/api/config')).json(); } catch (e) { log('config failed', e); }
  }
  async function join(role) {
    unlockAudio();
    let code = $('#sessionInput').value.trim();
    if (!code) {
      try { code = (await (await fetch('/api/new-session')).json()).session; } catch (e) { code = String(1000 + Math.floor(Math.random() * 9000)); }
    }
    S.role = role; S.session = code;
    S.lang = $('#langSelect').value || ROLE_DEFAULT_LANG[role];
    safeSet('interp.lang', S.lang);
    $('#langSelectCall').value = S.lang;
    S.sttMode = params.get('stt') || (S.config && S.config.default_stt_mode) || 'browser';
    document.body.classList.add('role-' + role);
    history.replaceState(null, '', `?session=${encodeURIComponent(code)}&role=${role}&lang=${S.lang}`);
    $('#sessionLabel').textContent = code;
    $('#join').classList.add('hidden'); $('#call').classList.remove('hidden');
    $('#micLabel').textContent = 'Tap to talk';
    connect();
    await showPairing();
    if (!window.isSecureContext) notice('This page is not secure (http), so the microphone is blocked. Use the https:// address.', 'bad', 0, 'insecure');
  }

  function wire() {
    if (!window.isSecureContext) $('#insecureBanner').classList.remove('hidden');
    const sess = params.get('session'); if (sess) $('#sessionInput').value = sess;
    const suggested = isMobile ? 'phone' : 'laptop';  // overridden below by ?role=
    document.querySelector(`.role-btn[data-role="${suggested}"]`).classList.add('suggested');
    document.querySelectorAll('.role-btn').forEach(b => b.addEventListener('click', () => join(b.dataset.role)));

    $('#micBtn').addEventListener('click', () => {
      if (S.micOn && isPaused()) { send({ type: 'interrupt' }); return; } // tap while paused = barge in
      setMic(!S.micOn);
    });
    $('#interruptBtn').addEventListener('click', () => { Player.flush(); send({ type: 'interrupt' }); });
    $('#settingsBtn').addEventListener('click', () => $('#drawer').classList.remove('hidden'));
    $('#closeDrawer').addEventListener('click', () => $('#drawer').classList.add('hidden'));
    $('#drawer').addEventListener('click', (e) => { if (e.target.id === 'drawer') $('#drawer').classList.add('hidden'); });
    document.querySelectorAll('#modeSeg button').forEach(b => b.addEventListener('click', () => switchMode(b.dataset.mode)));
    $('#selftestBtn').addEventListener('click', runSelftest);
    $('#testVoiceBtn').addEventListener('click', () => {
      unlockAudio();
      Player.enqueue({ kind: 'speak', order: -1, text: LANG[S.lang].test, lang: S.lang, provider: 'device' });
    });
    $('#leaveBtn').addEventListener('click', () => {
      S.closedByUser = true; setMic(false); Player.flush(); if (S.ws) S.ws.close();
      location.href = location.pathname;
    });
    // any tap re-enables sound if the browser suspended audio (screen lock, background tab)
    document.addEventListener('pointerdown', () => {
      if (S.audioCtx && S.audioCtx.state !== 'running') S.audioCtx.resume();
    });
    document.addEventListener('visibilitychange', () => {
      // Android stops recognition in background tabs; restart when visible again
      if (!document.hidden && S.micOn && S.recognizer) S.recognizer.resume();
      if (!document.hidden && S.audioCtx && S.audioCtx.state === 'suspended') S.audioCtx.resume();
    });

    // A link like ?session=1234&role=phone pre-selects everything, but we still wait for one
    // tap: browsers only allow sound/microphone after a user gesture.
    const role = params.get('role');
    // language: ?lang= > last used on this device > default for the seat this device would take
    const startLang = [params.get('lang'), safeGet('interp.lang')].find(l => l && LANG[l])
      || ROLE_DEFAULT_LANG[(role === 'laptop' || role === 'phone') ? role : suggested];
    $('#langSelect').value = startLang;
    $('#langSelectCall').addEventListener('change', async (e) => {
      const lang = e.target.value;
      if (!LANG[lang] || lang === S.lang) return;
      const wasOn = S.micOn;
      if (wasOn) await setMic(false);
      S.lang = lang; safeSet('interp.lang', lang);
      send({ type: 'lang', lang });
      updateVoiceInfo();
      if (wasOn) await setMic(true);
    });
    if (role === 'laptop' || role === 'phone') {
      document.querySelectorAll('.role-btn').forEach(b => b.classList.toggle('suggested', b.dataset.role === role));
      $('#joinHint').textContent = `Tap “${role === 'phone' ? 'Phone' : 'Laptop'}” to join session ${sess || ''}.`;
    }
    loadConfig();
  }

  wire();
})();
