// Voice is what the transcriber needs, not music: at 32 kbps a minute is ~240 KB instead of the
// ~900 KB Chrome records by default, so a long site visit stays far under the API's 10 MB limit.
const BITS_PER_SECOND = 32_000
// ~40 minutes fit in 10 MB at that rate; stopping earlier leaves room for a format that ignores it.
export const MAX_RECORDING_SECONDS = 30 * 60
// Chrome and Firefox record webm/Opus, Safari mp4/AAC; the API keeps whichever arrives.
const FORMATS = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4']

export type RecorderState = 'idle' | 'recording' | 'denied' | 'unsupported' | 'failed'

/**
 * One recording at a time from the microphone, with its elapsed time and a 0–1 input level for
 * the meter. While it records, the screen is kept on (Wake Lock) where the browser allows it.
 */
export function useRecorder() {
  const state = ref<RecorderState>('idle')
  const seconds = ref(0)
  const level = ref(0)

  let recorder: MediaRecorder | null = null
  let stream: MediaStream | null = null
  let audioContext: AudioContext | null = null
  let wakeLock: WakeLockSentinel | null = null
  let chunks: Blob[] = []
  let frame = 0
  let clock: ReturnType<typeof setInterval> | undefined

  const supported = () => import.meta.client && 'MediaRecorder' in window && !!navigator.mediaDevices?.getUserMedia

  async function keepScreenOn() {
    // Best effort: without it a phone that dims mid-dictation may pause the page.
    wakeLock = (await navigator.wakeLock?.request('screen').catch(() => null)) ?? null
  }
  // The browser drops the lock whenever the page is hidden; take it again on the way back.
  function onVisible() {
    if (document.visibilityState === 'visible' && state.value === 'recording') keepScreenOn()
  }

  function meter(source: MediaStream) {
    audioContext = new AudioContext()
    const analyser = audioContext.createAnalyser()
    analyser.fftSize = 512
    audioContext.createMediaStreamSource(source).connect(analyser)
    const samples = new Uint8Array(analyser.fftSize)
    const tick = () => {
      analyser.getByteTimeDomainData(samples)
      let sum = 0
      for (const sample of samples) sum += ((sample - 128) / 128) ** 2
      level.value = Math.min(1, Math.sqrt(sum / samples.length) * 4) // speech sits low: scale it up
      frame = requestAnimationFrame(tick)
    }
    tick()
  }

  function release() {
    cancelAnimationFrame(frame)
    clearInterval(clock)
    document.removeEventListener('visibilitychange', onVisible)
    stream?.getTracks().forEach((track) => track.stop())
    audioContext?.close()
    wakeLock?.release()
    recorder = stream = audioContext = wakeLock = null
    level.value = 0
  }

  async function start() {
    if (!supported()) {
      state.value = 'unsupported'
      return
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch (err) {
      state.value = (err as DOMException).name === 'NotAllowedError' ? 'denied' : 'failed'
      return
    }
    const mimeType = FORMATS.find((format) => MediaRecorder.isTypeSupported(format))
    recorder = new MediaRecorder(stream, { mimeType, audioBitsPerSecond: BITS_PER_SECOND })
    chunks = []
    recorder.ondataavailable = (event) => {
      if (event.data.size) chunks.push(event.data)
    }
    recorder.start(1000) // a chunk a second: a crash mid-recording loses a second, not the note
    seconds.value = 0
    clock = setInterval(() => seconds.value++, 1000)
    state.value = 'recording'
    meter(stream)
    document.addEventListener('visibilitychange', onVisible)
    keepScreenOn()
  }

  /** Stops and returns the recording. */
  async function stop(): Promise<Blob> {
    const active = recorder
    if (!active) throw new Error('Not recording')
    const stopped = new Promise((resolve) => active.addEventListener('stop', resolve, { once: true }))
    active.stop()
    await stopped
    const blob = new Blob(chunks, { type: active.mimeType })
    release()
    state.value = 'idle'
    return blob
  }

  /** Stops and throws the recording away. */
  function cancel() {
    if (recorder?.state === 'recording') recorder.stop()
    release()
    if (state.value === 'recording') state.value = 'idle'
  }

  onScopeDispose(cancel)

  return { state: readonly(state), seconds: readonly(seconds), level: readonly(level), start, stop, cancel }
}

export function formatDuration(totalSeconds: number) {
  return `${Math.floor(totalSeconds / 60)}:${String(totalSeconds % 60).padStart(2, '0')}`
}
