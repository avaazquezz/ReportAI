<script setup lang="ts">
// The page's proof without customers: the visitor dictates (or types) a short visit and the real
// pipeline fills the report in front of them (POST /demo/capture, then GET /demo/reports/{id} until
// it is ready). Limited per visitor and per day by the server; when it is off or full, the recorded
// sample visit takes its place.
import type { DemoFieldSpec } from '~/utils/demoFields'

type Phase = 'idle' | 'recording' | 'recorded' | 'sending' | 'working' | 'ready' | 'failed' | 'perIp' | 'full' | 'unavailable'

interface DemoReport {
  status: 'processing' | 'ready' | 'failed'
  document_type: string
  transcript: string | null
  fields: Record<string, unknown> | null
  field_schema: Record<string, DemoFieldSpec> | null
  missing: string[]
}

// The server's limit: about two minutes at the app's 32 kbps stays well under its 3 MB.
const MAX_SECONDS = 120
const POLL_MS = 2000
const GIVE_UP_MS = 120_000

const { t, locale } = useI18n()
const apiBase = useRuntimeConfig().public.apiBase
const cta = useTrialCta()
const recorder = useRecorder()

const phase = ref<Phase>('idle')
const typing = ref(false)
const text = ref('')
const audio = ref<Blob | null>(null)
const audioUrl = ref<string | null>(null)
const report = ref<DemoReport | null>(null)
const reportId = ref<string | null>(null)
const resultTitle = ref<HTMLElement | null>(null)

const pdfUrl = computed(() => (reportId.value ? `${apiBase}/demo/reports/${reportId.value}/pdf` : null))
const sample = computed(() => ({ audio: `/demo/audio-${locale.value}.mp3`, pdf: `/demo/informe-${locale.value}.pdf` }))
const busy = computed(() => phase.value === 'sending' || phase.value === 'working')
const canSend = computed(() => !busy.value && phase.value !== 'recording' && (!!audio.value || (typing.value && !!text.value.trim())))
const rows = computed(() =>
  demoRows(report.value?.field_schema ?? null, report.value?.fields ?? null, report.value?.missing ?? [], {
    locale: locale.value,
    yes: t('home.demo.yes'),
    no: t('home.demo.no')
  })
)
const message = computed(() => {
  const key = { working: 'working', ready: 'ready', failed: 'failed', perIp: 'perIp', full: 'full', unavailable: 'unavailable' }[phase.value as string]
  if (key) return t(`home.demo.states.${key}`)
  if (recorder.state.value === 'denied') return t('home.demo.states.denied')
  if (recorder.state.value === 'unsupported' || recorder.state.value === 'failed') return t('home.demo.states.noMic')
  return ''
})
const level = computed(() => recorder.level.value)
const BLANK = ['site', 'date', 'deficiency', 'company', 'measure', 'deadline'] as const
const blankRows = computed(() => BLANK.map((key) => ({ key, label: t(`home.hero.sheet.fields.${key}`), value: null })))

function setAudio(blob: Blob | null) {
  if (audioUrl.value) URL.revokeObjectURL(audioUrl.value)
  audio.value = blob
  audioUrl.value = blob ? URL.createObjectURL(blob) : null
}

async function record() {
  setAudio(null)
  await recorder.start()
  if (recorder.state.value === 'recording') phase.value = 'recording'
  else typing.value = true // no microphone: the written form is the way on
}

async function stop() {
  setAudio(await recorder.stop())
  phase.value = 'recorded'
}

// The recording stops itself at the server's limit rather than being refused after the fact.
watch(
  () => recorder.seconds.value,
  (seconds) => {
    if (seconds >= MAX_SECONDS && phase.value === 'recording') void stop()
  }
)

let polling: ReturnType<typeof setTimeout> | undefined
let startedAt = 0

async function poll() {
  if (!reportId.value) return
  try {
    report.value = await $fetch<DemoReport>(`/demo/reports/${reportId.value}`, { baseURL: apiBase, retry: 0 })
  } catch (error) {
    // A dropped poll is retried on the next tick; anything the server answered is final.
    if (!isUnreachable(error)) {
      phase.value = 'failed'
      return
    }
  }
  if (report.value?.status === 'ready') {
    phase.value = 'ready'
    await nextTick()
    resultTitle.value?.focus()
    return
  }
  if (report.value?.status === 'failed' || Date.now() - startedAt > GIVE_UP_MS) {
    phase.value = 'failed'
    return
  }
  polling = setTimeout(poll, POLL_MS)
}

async function send() {
  if (!canSend.value) return
  const body = new FormData()
  body.append('locale', locale.value)
  if (audio.value) body.append('audio', audio.value, `visita.${audio.value.type.includes('mp4') ? 'm4a' : 'webm'}`)
  if (typing.value && text.value.trim()) body.append('text', text.value.trim())
  phase.value = 'sending'
  report.value = null
  try {
    const created = await $fetch<{ id: string }>('/demo/capture', { baseURL: apiBase, method: 'POST', body, retry: 0 })
    reportId.value = created.id
  } catch (error) {
    phase.value = outcomeOf(error)
    return
  }
  phase.value = 'working'
  startedAt = Date.now()
  polling = setTimeout(poll, POLL_MS)
}

function outcomeOf(error: unknown): Phase {
  // No answer (no network, the API down, a browser that won't let the page read it): the visitor's
  // recording isn't what failed, so it isn't blamed; the recorded sample is offered instead.
  if (isUnreachable(error)) return 'unavailable'
  const response = (error as { response?: Response }).response
  if (!response) return 'failed'
  // 404: switched off. 402: the platform can't take it right now (its daily spend cap, AI not set
  // up); either way the recorded sample is what the visitor can have.
  if (response.status === 404 || response.status === 402) return 'unavailable'
  if (response.status === 429) return demoLimitHit((error as { data?: { detail?: unknown } }).data?.detail)
  return 'failed'
}

function reset() {
  clearTimeout(polling)
  setAudio(null)
  text.value = ''
  report.value = null
  reportId.value = null
  phase.value = 'idle'
}

const samplePlayer = ref<HTMLAudioElement | null>(null)
const samplePlaying = ref(false)
function toggleSample() {
  const player = samplePlayer.value
  if (!player) return
  if (player.paused) void player.play()
  else player.pause()
}

onBeforeUnmount(() => {
  clearTimeout(polling)
  recorder.cancel()
  setAudio(null)
})
</script>

<template>
  <section id="pruebalo" class="space-l border-t border-ink-900/10" aria-labelledby="demo-title">
    <div class="home-grid gap-y-14">
      <div class="col-span-12 lg:col-span-5">
        <h2 id="demo-title" class="t-section m-0">{{ t('home.demo.heading') }}</h2>
        <p class="t-lead m-0 mt-8 text-ink-900/80">{{ t('home.demo.sub') }}</p>
        <p class="t-body m-0 mt-5 text-ink-900/60">{{ t('home.demo.hint') }}</p>

        <div class="mt-10">
          <!-- Recording -->
          <div class="flex flex-wrap items-center gap-5">
            <button
              type="button"
              class="rec grid h-20 w-20 shrink-0 cursor-pointer place-items-center rounded-full border-0 text-white transition-transform duration-200 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
              :class="phase === 'recording' ? 'bg-ink-900' : 'bg-[#C0432A]'"
              :aria-pressed="phase === 'recording'"
              :disabled="busy"
              @click="phase === 'recording' ? stop() : record()"
            >
              <svg v-if="phase !== 'recording'" viewBox="0 0 24 24" class="h-8 w-8" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3" fill="currentColor" /><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" /></svg>
              <svg v-else viewBox="0 0 24 24" class="h-7 w-7" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="1.5" fill="currentColor" /></svg>
              <span class="sr-only">{{ phase === 'recording' ? t('home.demo.stop') : audio ? t('home.demo.again') : t('home.demo.record') }}</span>
            </button>
            <div class="min-w-0">
              <p class="m-0 font-semibold">
                {{ phase === 'recording' ? t('home.demo.recording') : audio ? t('home.demo.again') : t('home.demo.record') }}
              </p>
              <p v-if="phase === 'recording'" class="t-data m-0 mt-1 text-[#C0432A]" :aria-label="t('home.demo.timer')">{{ formatDuration(recorder.seconds.value) }}</p>
              <span v-if="phase === 'recording'" class="mt-2 flex h-6 items-center gap-[3px]" aria-hidden="true">
                <i v-for="n in 16" :key="n" class="block w-[3px] rounded-full bg-[#C0432A] transition-[height] duration-100" :style="{ height: `${4 + Math.round(level * 20 * (0.55 + ((n * 37) % 10) / 22))}px` }" />
              </span>
            </div>
          </div>
          <audio v-if="audioUrl && phase !== 'recording'" :src="audioUrl" controls class="mt-6 w-full max-w-md" />

          <!-- Or typed -->
          <button v-if="!typing" type="button" class="u-field mt-6 cursor-pointer border-0 bg-transparent p-0 text-[0.95rem] text-ink-900/75" @click="typing = true">
            {{ t('home.demo.orType') }}
          </button>
          <label v-else class="mt-6 block">
            <span class="text-[0.85rem] font-semibold">{{ t('home.demo.typeLabel') }}</span>
            <textarea
              v-model="text"
              rows="4"
              maxlength="2000"
              :placeholder="t('home.demo.typePlaceholder')"
              class="field-rule mt-2 block w-full resize-y border-x-0 border-t-0 bg-transparent px-0 py-2 text-[1rem] leading-relaxed outline-offset-4"
            />
          </label>

          <div class="mt-8 flex flex-wrap items-center gap-x-6 gap-y-3">
            <button type="button" class="btn-primary cursor-pointer border-0 disabled:cursor-not-allowed disabled:opacity-40" :disabled="!canSend" @click="send">
              {{ phase === 'sending' ? t('home.demo.sending') : t('home.demo.send') }}
            </button>
            <span class="text-[0.85rem] text-ink-900/60">{{ t('home.demo.limit') }}</span>
          </div>
          <p class="m-0 mt-6 max-w-md text-[0.8rem] leading-relaxed text-ink-900/60">{{ t('home.demo.privacy') }}</p>
        </div>
      </div>

      <!-- The report, filling in -->
      <div class="col-span-12 lg:col-span-6 lg:col-start-7">
        <p class="m-0 min-h-[1.5rem] text-[0.95rem] font-semibold" :class="phase === 'failed' || phase === 'perIp' || phase === 'full' ? 'text-[#C0432A]' : ''" role="status" aria-live="polite">
          {{ message }}
        </p>

        <div v-if="phase === 'perIp' || phase === 'full'" class="mt-4">
          <a :href="cta.href" class="btn-primary">{{ cta.label }}</a>
        </div>

        <div class="mt-5">
          <HomeActaSheet
            v-if="phase === 'ready' && report"
            :company="t('home.hero.sheet.company')"
            :title="report.document_type"
            :rows="rows"
            :empty-label="t('home.demo.empty')"
            :missing-label="t('home.demo.missing')"
          >
            <h3 ref="resultTitle" tabindex="-1" class="sr-only">{{ t('home.demo.resultTitle') }}</h3>
            <div v-if="report.transcript" class="mt-8 border-t border-ink-900/10 pt-5">
              <p class="m-0 text-[0.75rem] font-semibold text-ink-900/60">{{ t('home.demo.transcript') }}</p>
              <p class="m-0 mt-2 text-[0.9rem] leading-relaxed text-ink-900/75">{{ report.transcript }}</p>
            </div>
            <div class="mt-8 flex flex-wrap items-center gap-x-6 gap-y-3">
              <a v-if="pdfUrl" :href="pdfUrl" target="_blank" rel="noopener" class="btn-quiet">{{ t('home.demo.pdf') }}</a>
              <button type="button" class="u-field cursor-pointer border-0 bg-transparent p-0" @click="reset">{{ t('home.demo.reset') }}</button>
            </div>
          </HomeActaSheet>

          <!-- The blank form, waiting to be spoken into. -->
          <HomeActaSheet
            v-else
            class="demo-blank"
            :class="busy ? 'is-working' : 'hidden lg:block'"
            :company="t('home.hero.sheet.company')"
            :title="t('home.hero.sheet.title')"
            :rows="blankRows"
            empty-label=""
            aria-hidden="true"
          />
        </div>

        <!-- The recorded sample, always there for whoever can't or won't record -->
        <div class="mt-8 flex flex-wrap items-center gap-x-5 gap-y-3 text-[0.9rem]">
          <span class="text-ink-900/65">{{ t('home.demo.sample') }}</span>
          <button type="button" class="u-field cursor-pointer border-0 bg-transparent p-0 font-semibold" @click="toggleSample">
            {{ samplePlaying ? t('home.demo.samplePause') : t('home.demo.samplePlay') }}
          </button>
          <a :href="sample.pdf" target="_blank" rel="noopener" class="u-field">{{ t('home.demo.samplePdf') }}</a>
          <audio ref="samplePlayer" :src="sample.audio" preload="none" @play="samplePlaying = true" @pause="samplePlaying = false" @ended="samplePlaying = false" />
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* While the pipeline works, the blank form's rules breathe: something is being written. */
.demo-blank.is-working :deep(.field-rule) {
  animation: rule-breathe 1.4s var(--ease-ra) infinite alternate;
}
@keyframes rule-breathe {
  from {
    border-bottom-color: var(--acta-rule);
  }
  to {
    border-bottom-color: var(--acta-red);
  }
}
@media (prefers-reduced-motion: reduce) {
  .demo-blank.is-working :deep(.field-rule) {
    animation: none;
    border-bottom-color: var(--acta-red);
  }
}
</style>
