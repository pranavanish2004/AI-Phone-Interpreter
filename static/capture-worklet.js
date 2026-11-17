// AudioWorklet: microphone (48 kHz / 44.1 kHz float) -> 16 kHz mono PCM16, 20 ms frames.
// Posts {pcm: ArrayBuffer(640 bytes), rms: number} to the main thread.
class CaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / 16000;      // `sampleRate` is a global in the worklet scope
    this.pos = 0;                          // fractional read position into the incoming stream
    this.prev = 0;                         // last sample of previous block (for interpolation)
    this.frame = new Int16Array(320);
    this.fill = 0;
    this.sumSq = 0;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0]) return true;
    const ch = input[0];
    const n = ch.length;
    // linear-interpolation resampler; `pos` is relative to the start of this block,
    // index -1 refers to `this.prev`
    while (this.pos < n - 1) {
      const i = Math.floor(this.pos);
      const frac = this.pos - i;
      const a = i < 0 ? this.prev : ch[i];
      const b = ch[i + 1];
      let s = a + (b - a) * frac;
      s = Math.max(-1, Math.min(1, s));
      const v = s < 0 ? s * 0x8000 : s * 0x7fff;
      this.frame[this.fill++] = v;
      this.sumSq += v * v;
      if (this.fill === this.frame.length) {
        const rms = Math.sqrt(this.sumSq / this.frame.length);
        const out = this.frame.buffer.slice(0);
        this.port.postMessage({ pcm: out, rms }, [out]);
        this.fill = 0;
        this.sumSq = 0;
      }
      this.pos += this.ratio;
    }
    this.pos -= n;
    this.prev = ch[n - 1];
    return true;
  }
}
registerProcessor('capture-processor', CaptureProcessor);
