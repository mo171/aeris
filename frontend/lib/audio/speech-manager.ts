class SpeechManager {
  private currentAudio: HTMLAudioElement | null = null;
  private currentUtteranceId: string | null = null;
  private queue: { url: string; interruptible: boolean; id: string }[] = [];

  play(url: string, utteranceId: string, interruptible: boolean) {
    if (this.currentAudio && !this.currentAudio.paused) {
      if (interruptible) {
        this.currentAudio.pause();
        this.currentAudio.currentTime = 0;
      } else {
        this.queue.push({ url, interruptible, id: utteranceId });
        return;
      }
    }
    this.currentUtteranceId = utteranceId;
    this.currentAudio = new Audio(url);
    this.currentAudio.onended = () => {
      this.currentAudio = null;
      this.currentUtteranceId = null;
      if (this.queue.length > 0) {
        const next = this.queue.shift()!;
        this.play(next.url, next.id, next.interruptible);
      }
    };
    this.currentAudio.play().catch(e => console.error("Audio play failed:", e));
  }

  stop() {
    if (this.currentAudio) {
      this.currentAudio.pause();
      this.currentAudio.currentTime = 0;
      this.currentAudio = null;
    }
    this.queue = [];
    this.currentUtteranceId = null;
  }
}
export const speechManager = new SpeechManager();
