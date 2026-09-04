<script setup lang="ts">
const { t, locale } = useI18n()

// Real pipeline output, generated once via backend/scripts/generate_landing_demo_audio.py
// (real OpenAI TTS) + generate_landing_demo_asset.py (real Groq Whisper transcription,
// real Claude extraction, real docxtpl+Gotenberg render). Not a live call — see
// PROJECT_ROADMAP.md decisions log, 2026-08-15. Two independent real runs (one per
// locale), not a translation of one into the other. The page images are the PDFs
// rendered with pdftoppm at 120 dpi.
const TRANSCRIPT_ES =
  'Hola, buenas tardes. Soy Javier Molina. Hoy, 18 de agosto, acabo de terminar la ' +
  'reunión con Construcciones Marítimas del Levante, en sus oficinas de Alicante. Han ' +
  'asistido Marta Delgado, la directora de compras, Oscar Ferreira, del departamento ' +
  'técnico, y Laura Sanz, responsable de logística. Hemos repasado tres puntos. Primero, ' +
  'el pedido trimestral, que sube un 15% a partir de octubre. Segundo, la ampliación del ' +
  'contrato de mantenimiento a dos años. Y tercero, el cambio de proveedor de transporte ' +
  'para las entregas del sur. Se ha decidido aceptar el incremento de volumen, reduciendo ' +
  'el plazo de entrega a dos semanas, y renovar el contrato de mantenimiento con las ' +
  'condiciones actuales. Como acciones, yo, Javier Molina, debo enviar la propuesta ' +
  'actualizada a Marta antes del viernes 21 de agosto. Oscar confirmará la disponibilidad ' +
  'de almacén el lunes 24 de agosto. Y Laura tiene que contactar con el nuevo ' +
  'transportista antes de fin de mes. Quedamos en vernos otra vez el 15 de septiembre ' +
  'para cerrar el tema del transporte. En general, muy buena reunión.'

const TRANSCRIPT_EN =
  'Hi, good afternoon. This is James Whitfield. Today, August 18th, I just wrapped up ' +
  'the meeting with Harbor Point Industrial Supply at their offices in Savannah, ' +
  'Georgia. In attendance were Sarah Mitchell, VP of Procurement, Marcus Reed from the ' +
  'Technical Department, and Emily Chen, who handles logistics. We went over three ' +
  'items. First, the quarterly order, which is going up 15% starting in October. ' +
  'Second, extending the maintenance contract to two years. And third, changing the ' +
  'freight carrier for deliveries to the southern region. We agreed to accept the ' +
  'volume increase by cutting the delivery window down to two weeks and to renew the ' +
  'maintenance contract on the current terms. As for next steps, I, James Whitfield, ' +
  'need to send the updated proposal to Sarah by Friday, August 21. Marcus will ' +
  'confirm warehouse availability on Monday, August 24, and Emily has to reach out to ' +
  'the new carrier before the end of the month. We\'re set to meet again on ' +
  'September 15th to close out the transport piece.'

const FIELDS_ES = [
  { label: 'company_name', value: 'Construcciones Marítimas del Levante' },
  { label: 'meeting_date', value: '2025-08-18' },
  { label: 'attendees', value: 'Javier Molina, Marta Delgado, Óscar Ferreira, Laura Sanz' },
  { label: 'decisions', value: 'Aceptar el incremento de volumen (15%), reduciendo el plazo de entrega a dos semanas' },
  { label: 'action_items', value: 'Enviar la propuesta a Marta — Javier Molina, 21/08' }
]

const FIELDS_EN = [
  { label: 'company_name', value: 'Harbor Point Industrial Supply' },
  { label: 'meeting_date', value: '2024-08-18' },
  { label: 'attendees', value: 'James Whitfield, Sarah Mitchell, Marcus Reed, Emily Chen' },
  { label: 'decisions', value: 'Accept the volume increase (15%), reducing the delivery window to two weeks' },
  { label: 'action_items', value: 'Send the updated proposal to Sarah — James Whitfield, 08/21' }
]

const content = computed(() =>
  locale.value === 'es'
    ? { transcript: TRANSCRIPT_ES, fields: FIELDS_ES, audioSrc: '/demo/audio-es.mp3', pdfSrc: '/demo/informe-es.pdf', pageSrc: '/demo/informe-es.png' }
    : { transcript: TRANSCRIPT_EN, fields: FIELDS_EN, audioSrc: '/demo/audio-en.mp3', pdfSrc: '/demo/informe-en.pdf', pageSrc: '/demo/informe-en.png' }
)

// One caption per sentence, shown in step with the audio. The narration has no word
// timestamps, so each sentence's share of the characters stands in for its share of
// the speaking time — close enough to read as "it's transcribing what you hear".
const sentences = computed(() => content.value.transcript.split(/(?<=[.])\s+/))
const sentenceStarts = computed(() => {
  const total = content.value.transcript.length
  let consumed = 0
  return sentences.value.map((s) => {
    const start = consumed / total
    consumed += s.length + 1
    return start
  })
})
// Extraction is shown catching up behind the transcript, one field at a time.
const FIELD_STARTS = [0.3, 0.44, 0.58, 0.72, 0.86]

const audioEl = ref<HTMLAudioElement | null>(null)
const playing = ref(false)
const played = ref(false)
const currentTime = ref(0)
const duration = ref(0)

const progress = computed(() => (duration.value ? currentTime.value / duration.value : 0))
const visibleSentences = computed(() => (played.value ? sentenceStarts.value.filter((s) => s <= progress.value + 0.02).length : 0))
const visibleFields = computed(() => (played.value ? FIELD_STARTS.filter((s) => s <= progress.value).length : 0))

function formatTime(seconds: number): string {
  const s = Math.floor(seconds % 60)
  const m = Math.floor(seconds / 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function togglePlay() {
  if (!audioEl.value) return
  if (audioEl.value.paused) audioEl.value.play()
  else audioEl.value.pause()
}

function seek(event: Event) {
  if (!audioEl.value) return
  audioEl.value.currentTime = Number((event.target as HTMLInputElement).value)
}

function onPlay() {
  playing.value = true
  played.value = true
}
function onPause() {
  playing.value = false
}
function onEnded() {
  playing.value = false
  // Guarantees every caption and field is shown even if the last timeupdate fell short.
  currentTime.value = duration.value
}
function onTimeUpdate() {
  if (audioEl.value) currentTime.value = audioEl.value.currentTime
}
function onLoadedMetadata() {
  if (audioEl.value) duration.value = audioEl.value.duration
}

// The SSR-rendered <audio preload="metadata"> can finish loading before hydration
// attaches the listener above, in which case `loadedmetadata` has already fired.
onMounted(() => {
  if (audioEl.value && audioEl.value.readyState >= 1) onLoadedMetadata()
})

// A locale switch swaps the audio source: reset the player so the captions don't
// keep the other language's progress.
watch(locale, () => {
  played.value = false
  playing.value = false
  currentTime.value = 0
})

const root = ref<HTMLElement | null>(null)
useSectionMotion(root, (tl) => {
  tl.fromTo('.head', { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.5 })
    .fromTo('.player', { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.55 }, '-=0.2')
    .fromTo('.page', { opacity: 0, y: 28, rotate: 1.5 }, { opacity: 1, y: 0, rotate: 0, duration: 0.7 }, '-=0.35')
})
</script>

<template>
  <section id="ejemplo-real" ref="root" class="bg-paper-50 py-20 md:py-28">
    <div class="mx-auto max-w-[1200px] px-6">
      <div class="head m-hide max-w-2xl">
        <h2 class="font-display text-[clamp(1.9rem,3.4vw,2.9rem)] font-bold leading-[1.05] tracking-[-0.02em] text-ink-900">
          {{ t('landing.realDemo.heading') }}
        </h2>
        <p class="mt-4 font-body text-lg leading-relaxed text-ink-900/75">{{ t('landing.realDemo.paragraph') }}</p>
      </div>

      <div class="mt-12 grid items-start gap-10 lg:grid-cols-[1fr_0.92fr] lg:gap-14">
        <div class="player m-hide rounded-2xl bg-surface-0 p-6 shadow-page md:p-8">
          <audio
            ref="audioEl"
            :src="content.audioSrc"
            preload="metadata"
            class="hidden"
            @play="onPlay"
            @pause="onPause"
            @ended="onEnded"
            @timeupdate="onTimeUpdate"
            @loadedmetadata="onLoadedMetadata"
          />
          <div class="flex items-center gap-4">
            <button
              type="button"
              class="flex h-14 w-14 shrink-0 cursor-pointer items-center justify-center rounded-full border-0 bg-capture-600 text-white transition-transform hover:scale-105"
              :aria-label="playing ? t('landing.realDemo.pause') : t('landing.realDemo.play')"
              @click="togglePlay"
            >
              <svg v-if="!playing" viewBox="0 0 20 20" fill="currentColor" class="ml-0.5 h-6 w-6" aria-hidden="true">
                <path d="M6 4.5v11l9-5.5-9-5.5Z" />
              </svg>
              <svg v-else viewBox="0 0 20 20" fill="currentColor" class="h-6 w-6" aria-hidden="true">
                <path d="M6 4.5h3v11H6v-11Zm5 0h3v11h-3v-11Z" />
              </svg>
            </button>
            <div class="flex-1">
              <input
                type="range"
                min="0"
                :max="duration || 0"
                step="0.1"
                :value="currentTime"
                :aria-label="t('landing.realDemo.seek')"
                class="block h-1.5 w-full cursor-pointer accent-capture-600"
                @input="seek"
              >
              <div class="mt-1.5 flex justify-between font-mono text-xs text-ink-900/50">
                <span>{{ formatTime(currentTime) }}</span>
                <span>{{ formatTime(duration) }}</span>
              </div>
            </div>
          </div>

          <div class="mt-7 border-t border-paper-100 pt-5">
            <p class="font-body text-xs font-semibold text-ink-900/50">{{ t('landing.realDemo.transcriptLabel') }}</p>
            <div class="mt-2 min-h-[9rem] font-body text-[15px] leading-relaxed">
              <p v-if="!played" class="text-ink-900/40">{{ t('landing.realDemo.playPlaceholder') }}</p>
              <p v-else>
                <span
                  v-for="(sentence, i) in sentences"
                  :key="i"
                  class="inline transition-[opacity,color] duration-500 ease-out"
                  :class="i < visibleSentences ? (i === visibleSentences - 1 ? 'text-ink-900' : 'text-ink-900/60') : 'opacity-0'"
                >{{ `${sentence} ` }}</span>
              </p>
            </div>
          </div>

          <div class="mt-6 border-t border-paper-100 pt-5">
            <p class="font-body text-xs font-semibold text-ink-900/50">{{ t('landing.realDemo.fieldsLabel') }}</p>
            <ul class="mb-0 mt-2 list-none space-y-1.5 pl-0 font-mono text-xs leading-5 text-ink-900">
              <li
                v-for="(field, i) in content.fields"
                :key="field.label"
                class="transition-[opacity,transform] duration-500 ease-out"
                :class="i < visibleFields ? 'translate-y-0 opacity-100' : 'translate-y-1 opacity-0'"
              >
                <span class="text-capture-600">{{ field.label }}:</span> {{ field.value }}
              </li>
            </ul>
          </div>
        </div>

        <div class="page m-hide">
          <div class="flex items-baseline justify-between gap-4">
            <p class="font-body text-xs font-semibold text-ink-900/50">{{ t('landing.realDemo.documentLabel') }}</p>
            <p class="font-mono text-[11px] text-ink-900/50">{{ t('landing.realDemo.pageMeta') }}</p>
          </div>
          <div class="mt-2 overflow-hidden rounded-[3px] bg-surface-0 shadow-page">
            <img
              :src="content.pageSrc"
              :alt="t('landing.realDemo.pageAlt')"
              width="1020"
              height="1320"
              loading="lazy"
              decoding="async"
              class="block h-auto w-full"
            >
          </div>
          <div class="mt-4 flex flex-wrap items-start justify-between gap-4">
            <p v-if="t('landing.realDemo.note')" class="max-w-md font-body text-sm leading-relaxed text-ink-900/60">
              {{ t('landing.realDemo.note') }}
            </p>
            <a
              :href="content.pdfSrc"
              download
              class="ml-auto inline-flex items-center gap-2 rounded-md bg-ink-900 px-4 py-2.5 font-body text-sm font-semibold text-white transition-colors hover:bg-capture-600"
            >
              <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" class="h-4 w-4" aria-hidden="true">
                <path d="M10 3v10m0 0 4-4m-4 4-4-4M4 17h12" />
              </svg>
              {{ t('landing.realDemo.downloadPdf') }}
            </a>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
