# AI Phone Interpreter: English ⇄ Telugu ⇄ Tamil ⇄ Hindi (two devices)

Two people, two devices, one conversation. Each person picks **their own language** when they join
(English, తెలుగు Telugu, தமிழ் Tamil or हिन्दी Hindi). Whatever one person says is translated into the
other person's language and spoken aloud on the other device. Any pair works, e.g. Telugu ⇄ Tamil.

The two seats are called **Laptop** and **Phone**, but they are just seats: either can be a laptop or a phone.

Both screens show the live transcript, the translation, which device is online or playing, and the latency.

## Quick start (Windows laptop)

1. **Start the server.** Double-click **`start.bat`**. It uses your Anaconda Python, which already has every
   package this project needs. On first run it creates `.env` and a self-signed HTTPS certificate.
   * If Windows Firewall asks, choose **Allow** for **Private networks**. Without this the phone cannot connect.
2. **Laptop:** open **http://localhost:8000** in Chrome or Edge. Tap **Laptop**.
3. **Phone:** connect to the **same Wi-Fi** as the laptop. Scan the QR code on the laptop screen, or type the
   `https://<laptop-ip>:8443/...` address printed in the server window into **Chrome**.
   * Chrome warns *"Your connection is not private"*. Tap **Advanced → Proceed**. You only do this once;
     the certificate is our own local one.
   * Tap **Phone**. When asked, allow the microphone.
4. Tap the **mic button** on both devices and talk.

You need no API keys for this. The free path is:

| Stage | Default (free, no key) | Optional upgrade |
|---|---|---|
| Speech → text | Chrome's built-in recognition on each device (`en-IN`, `te-IN`, `ta-IN`, `hi-IN`) | Azure Speech, server-side (Settings → *Azure (server)*) |
| Translation | Google free endpoint, then MyMemory if that fails | Azure AI Translator (tried first when a key is set) |
| Text → speech | **Edge TTS** neural voices (`pip install edge-tts`), then the **Google Translate voice**, then the device's own voice | Azure neural voices (same voice names as Edge); ElevenLabs (`eleven_v3`, ~10 min/month free) |

Edge TTS and the Google voice are free and need no account, but they are **unofficial** services: they could
change or rate-limit at any time, which is why the app always has a fallback ready.

Every stage falls back to the next option automatically. A broken key shows a notice; it does not stop the conversation.

## Check the real cloud services

```
run_tests.bat
```

This runs the offline test suite, then **`python scripts/stage1_probe.py --translator-diagnose`**. The probe makes
real network calls and prints OK/FAIL with timings for:

* translation en→te and te→en with each provider
* Azure TTS in Telugu and English
* an Azure STT round trip: Azure synthesises a Telugu or English sentence, then Azure recognises it again
* for an Azure Translator `401001` error, it retries with each region-header variant and tells you the exact
  `AZURE_TRANSLATOR_REGION` value that works

The same check is available in the app under **⚙ Settings → Run live provider check**, or at `/api/selftest`.

### Why the earlier Azure Translator call returned 401001

`401001` means Azure rejected the credentials. Common causes:

1. **Region header.** A regional or multi-service Translator resource needs `Ocp-Apim-Subscription-Region`
   set to the resource's *Location*, for example `centralindia`. A *Global* resource needs no region.
   Set `AZURE_TRANSLATOR_REGION` to match. The probe finds the right value for you.
2. **Wrong key.** A Speech key was pasted as the Translator key. The probe flags it if both keys are identical.
3. The key was regenerated in the portal.

The fix in code: requests now send the region header only when it is configured. The endpoint accepts the global
URL or a custom `*.cognitiveservices.azure.com` domain, and either path form copied from the portal.

### ElevenLabs 402 `paid_plan_required`

Telugu library voices need a paid ElevenLabs plan, so ElevenLabs is optional and English-only here. Telugu uses
Azure's free `te-IN-ShrutiNeural` voice when a Speech key is set, and the phone's built-in Telugu voice otherwise.

## How it works

```
 PHONE (Chrome, te-IN)                     LAPTOP: python run.py                       LAPTOP BROWSER (en-IN)
 ─────────────────────                     ─────────────────────                       ──────────────────────
 mic → SpeechRecognition ──"final" text──▶ loopguard ─▶ translate (Azure│Google│MyMemory)
   (or PCM 16 kHz frames ──binary──▶ VAD ─▶ Azure STT ─┘          │
                                                     sentences ─▶ TTS (Azure│device voice)
                                                                   │
                      ◀───────── audio/speak messages ─────────────┴──────────▶ playback queue → speaker
```

| File | Role |
|---|---|
| `run.py` | Starts one app on **two listeners**: `http://localhost:8000` for the laptop and `https://<ip>:8443` for the phone |
| `server/app.py` | FastAPI routes plus the `/ws` WebSocket protocol (documented in the module docstring) |
| `server/session.py` | Sessions and rooms: one laptop and one phone per session code, with a per-speaker ordered work queue |
| `server/pipeline.py` | STT → translate → sentence split → TTS (in parallel, delivered in order) → other device. Also handles interrupts and latency |
| `server/stt.py` | Azure Speech REST short-audio STT, WAV helpers and mock |
| `server/translate.py` | Azure Translator, Google free, MyMemory and mock, with a fallback chain and cooldown on auth errors |
| `server/tts.py` | Azure neural TTS, ElevenLabs (English only), browser-voice fallback and mock |
| `server/vad.py` | Adaptive energy VAD that cuts streamed audio into utterances |
| `server/loopguard.py` | Feedback-loop prevention (see below) |
| `server/sentences.py` | Sentence chunking, including Indic `।` |
| `server/latency.py` | Per-stage timing, median and p90 |
| `server/selftest.py` | Live provider checks |
| `static/` | UI. `app.js` handles recognition, playback queue and UI; `capture-worklet.js` handles 48 kHz → 16 kHz PCM |

### Feedback loops and interruptions

When the laptop plays English, the phone's mic could hear it and send it back for translation. Three
layers prevent this:

1. While **any** device plays translated audio, both devices pause recognition. The server also drops any text
   or audio that arrives during playback.
2. The pause lasts 0.6 s past the end of playback, to cover room echo.
3. A longer transcript that arrives within 1 s of playback and repeats what was just played is dropped as an echo.

To **interrupt**, tap **■ Stop audio**, or tap the mic while it shows *Paused*. Playback stops on every device,
queued sentences are discarded, and both mics reopen.

## Troubleshooting

| Problem | Fix |
|---|---|
| Phone can't open the page | Same Wi-Fi? Firewall allowed for *Private* networks? Campus Wi-Fi often blocks device-to-device traffic. If so, turn on the **phone's hotspot** and connect the laptop to it, then restart `start.bat` so it picks up the new IP. |
| "Microphone blocked" | The phone must use **https://** and laptop must use `http://localhost` (not `http://<ip>`). |
| No Telugu voice on phone | Android **Settings → Text-to-speech output → Google → Install voice data → Telugu**. Adding an Azure Speech key also fixes this. |
| Recognition says "network" | Chrome's recognition uses Google's servers, so the phone needs internet. Or use **⚙ → Azure (server)**. |
| Nothing plays | Tap the screen once. Browsers need a tap before they play sound. |
| Firefox or Samsung Internet | Use **Chrome**, which supports speech recognition. |

## Deploy for a demo (open from any laptop/phone, anywhere)

Running on your own laptop needs both devices on the same Wi-Fi, and shows a certificate
warning on the phone. For an interview where people join from their *own* laptops, deploy
to a free host instead: it gives a real `https://...` link that works from anywhere with no
warning, and you don't need to run anything locally.

**[Render.com](https://render.com)** is the easiest option (free tier, no command line needed):

1. Put this project in a GitHub repo (if it isn't already):
   ```
   git init
   git add .
   git commit -m "AI phone interpreter"
   ```
   Create a new repo on github.com, then follow the push instructions it shows you.
2. Go to [render.com](https://render.com) → sign up (free, e.g. with your GitHub account).
3. **New +** → **Blueprint** → pick your repo. Render reads `render.yaml` in this project and
   fills in the build/start commands automatically. Click **Apply**.
   (No Blueprint option? Use **New + → Web Service** instead, pick the repo, and set:
   *Build Command* `pip install -r requirements.txt`, *Start Command* `python run.py --cloud`.)
4. Wait for the first deploy (a few minutes). Render gives you a URL like
   `https://ai-phone-interpreter-xxxx.onrender.com`.
5. Share that single link. Anyone who opens it picks **Laptop** or **Phone** and joins with the
   same session code - works on real HTTPS, no same-Wi-Fi requirement, no certificate warning.
6. *(Optional)* Add your Azure/ElevenLabs keys under the service's **Environment** tab in the
   Render dashboard - never put real keys in `render.yaml` or commit `.env`.

**Free-tier catch:** Render puts a free service to sleep after 15 minutes idle; the next visit
takes ~30-50 seconds to wake up. **Open the link yourself 5 minutes before the interview** so
it's already warm when you demo it. If that's not reliable enough, Railway.app and Fly.io are
similar free alternatives with less aggressive sleep - same `render.yaml` values work as their
build/start commands too.

**Also record a 1-2 minute screen capture of it working**, as a backup in case Wi-Fi, a cold
start, or a microphone permission trips up the live demo.

## Tests

```
python -m pytest                       # 68 offline tests: providers vs a fake Azure/Google/MyMemory HTTP server,
                                       # VAD, loop guard, sentences, latency, config, full WebSocket protocol
python scripts/ws_smoke.py             # two fake devices against a RUNNING server (real providers if keys set)
python scripts/e2e_browser.py          # (dev, needs playwright) two real Chromium devices incl. fake microphone
```
