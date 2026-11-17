# Demo script (about 5 minutes)

**Setup:** start the server (`python run.py`, or `start.bat` on Windows). Both people open the link in Chrome,
enter the same session code, pick their language under **"I speak"**, and take one seat each (**Laptop** / **Phone**).
Both device cards should show **online**, each with its language.

1. **Telugu → English.** The Telugu speaker taps the mic and says *"నమస్కారం, మీరు ఎలా ఉన్నారు?"*.
   The other screen shows the Telugu text live, then *"Hello, how are you?"*, and speaks it.
   While it plays, the speaker's mic shows *Paused*. That is the feedback-loop guard.
2. **English → Telugu.** The English speaker says *"I am fine. Where is the railway station?"*.
   The other device speaks the Telugu translation, one sentence at a time.
3. **Switch language.** In **⚙ Settings → My language**, change one side to **Tamil** or **Hindi** and keep talking.
4. **Latency.** The strip above the mic shows translation, voice and first-audio times; each bubble shows its own breakdown.
5. **Interrupt.** Say a long sentence. While it plays, tap **■ Stop audio**. Playback stops and both mics reopen.
6. **Provider check.** **⚙ Settings → Run live provider check** shows which real services answered and how fast.

Speak in short sentences and pause briefly at the end, so the recognizer knows you have finished.
