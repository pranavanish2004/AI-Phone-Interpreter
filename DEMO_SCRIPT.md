# Demo script (about 5 minutes)

**Setup:** run `start.bat`. Open `http://localhost:8000` on the laptop and tap **Laptop**. Scan the QR code with the
phone, tap **Proceed**, then tap **Phone**. Both device cards should show **online** in green.

1. **Telugu → English.** On the phone, tap the mic and say *"నమస్కారం, మీరు ఎలా ఉన్నారు?"*.
   The laptop shows the live Telugu text as it is spoken, then *"Hello, how are you?"*, and speaks it.
   While the laptop speaks, the phone's mic shows *Paused · other device playing*. That is the loop guard.
2. **English → Telugu.** On the laptop, tap the mic and say *"I am fine. Where is the railway station?"*.
   The phone speaks the Telugu translation one sentence at a time.
3. **Latency.** The strip above the mic shows translate, voice and first-audio times. Each bubble shows its own
   breakdown, and the medians for each direction appear on the laptop.
4. **Interrupt.** Say a long sentence on the laptop. While the phone is speaking, tap **■ Stop audio**.
   Playback stops on the phone and both mics reopen.
5. **Provider check.** Go to **⚙ Settings → Run live provider check**. It shows which real services answered and
   how fast.

Speak in short sentences and pause briefly at the end, so the recognizer knows you have finished.
