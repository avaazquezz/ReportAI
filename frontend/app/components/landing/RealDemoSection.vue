<script setup lang="ts">
import gsap from 'gsap'

// Real pipeline output, generated once via backend/scripts/generate_landing_demo_audio.py
// (real OpenAI TTS) + generate_landing_demo_asset.py (real Groq Whisper transcription,
// real Claude extraction, real docxtpl+Gotenberg render). Not a live call — see
// PROJECT_ROADMAP.md decisions log, 2026-08-15.
const TRANSCRIPT =
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

const FIELDS = [
  { label: 'company_name', value: 'Construcciones Marítimas del Levante' },
  { label: 'meeting_date', value: '2025-08-18' },
  { label: 'attendees', value: 'Javier Molina, Marta Delgado, Óscar Ferreira, Laura Sanz' },
  {
    label: 'decisions',
    value: 'Aceptar el incremento de volumen (15%), reduciendo el plazo de entrega a dos semanas'
  },
  {
    label: 'action_items',
    value: 'Enviar la propuesta a Marta — Javier Molina, 21/08'
  }
]

const EXTRACTION_COST_USD = 0.018147
const eyebrowTag = '{{ ejemplo_real }}'

// One reveal "line" per sentence — natural caption-style stagger, and a clean
// 1:1 index into transcriptLines (no word-grouping math to get wrong).
const TRANSCRIPT_SENTENCES = TRANSCRIPT.split(/(?<=[.])\s+/)

const root = ref<HTMLElement | null>(null)
const audioEl = ref<HTMLAudioElement | null>(null)
const transcriptLines = ref<HTMLElement[]>([])
const fieldRows = ref<HTMLElement[]>([])
const documentCard = ref<HTMLElement | null>(null)

const playing = ref(false)
const played = ref(false)
const currentTime = ref(0)
const duration = ref(0)

function setTranscriptRef(el: unknown, i: number) {
  if (el) transcriptLines.value[i] = el as HTMLElement
}
function setFieldRef(el: unknown, i: number) {
  if (el) fieldRows.value[i] = el as HTMLElement
}

const progressPct = computed(() => (duration.value ? (currentTime.value / duration.value) * 100 : 0))

function formatTime(seconds: number): string {
  const s = Math.floor(seconds % 60)
  const m = Math.floor(seconds / 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function togglePlay() {
  if (!audioEl.value) return
  if (audioEl.value.paused) {
    audioEl.value.play()
  } else {
    audioEl.value.pause()
  }
}

function seek(event: MouseEvent) {
  if (!audioEl.value || !duration.value) return
  const bar = event.currentTarget as HTMLElement
  const ratio = (event.clientX - bar.getBoundingClientRect().left) / bar.clientWidth
  audioEl.value.currentTime = ratio * duration.value
}

function revealSequence() {
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches

  if (prefersReducedMotion) {
    gsap.set([...transcriptLines.value, ...fieldRows.value, documentCard.value], {
      opacity: 1,
      y: 0
    })
    return
  }

  gsap
    .timeline()
    .fromTo(
      transcriptLines.value,
      { opacity: 0, y: 8 },
      { opacity: 1, y: 0, duration: 0.5, stagger: 0.25, ease: 'power1.out' }
    )
    .fromTo(
      fieldRows.value,
      { opacity: 0, y: 10 },
      { opacity: 1, y: 0, duration: 0.4, stagger: 0.15, ease: 'power1.out' },
      '+=0.2'
    )
    .fromTo(
      documentCard.value,
      { opacity: 0, y: 16, scale: 0.98 },
      { opacity: 1, y: 0, scale: 1, duration: 0.5, ease: 'back.out(1.7)' },
      '+=0.15'
    )
}

async function onPlay() {
  playing.value = true
  if (!played.value) {
    played.value = true
    // The transcript spans only exist in the DOM once Vue re-renders the v-else
    // branch this flips on — GSAP would otherwise animate an empty ref array.
    await nextTick()
    revealSequence()
  }
}
function onPause() {
  playing.value = false
}
function onTimeUpdate() {
  if (audioEl.value) currentTime.value = audioEl.value.currentTime
}
function onLoadedMetadata() {
  if (audioEl.value) duration.value = audioEl.value.duration
}
</script>

<template>
  <section
    id="ejemplo-real"
    ref="root"
    class="mx-auto max-w-[1200px] px-6 py-16 md:py-24"
    style="background: radial-gradient(circle at 30% 20%, rgba(18, 21, 28, 0.04), transparent 60%)"
  >
    <LandingRevealOnScroll>
      <div class="mb-10 text-center">
        <p class="mb-2 font-mono text-xs uppercase tracking-wide text-capture-600">
          {{ eyebrowTag }}
        </p>
        <h2 class="font-display text-3xl font-bold text-ink-900 md:text-4xl">Esto no es una maqueta.</h2>
        <p class="mx-auto mt-3 max-w-xl font-body text-base text-ink-900/70">
          Es la salida real del sistema: una nota de voz de verdad, transcrita por Groq Whisper,
          extraída por Claude y rellenada en la plantilla — sin editar nada después. Dale a play.
        </p>
      </div>

      <div
        class="grid gap-8 rounded-2xl bg-surface-0 p-6 shadow-2xl md:grid-cols-2 md:p-10"
        style="box-shadow: 0 20px 60px -15px rgba(255, 106, 69, 0.25)"
      >
        <!-- Left: audio + transcript -->
        <div>
          <audio
            ref="audioEl"
            src="/demo/audio.mp3"
            preload="metadata"
            class="hidden"
            @play="onPlay"
            @pause="onPause"
            @ended="onPause"
            @timeupdate="onTimeUpdate"
            @loadedmetadata="onLoadedMetadata"
          />
          <div class="flex items-center gap-4">
            <button
              type="button"
              class="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-capture-600 text-white transition-transform hover:scale-105"
              :aria-label="playing ? 'Pausar' : 'Reproducir'"
              @click="togglePlay"
            >
              <svg v-if="!playing" viewBox="0 0 20 20" fill="currentColor" class="ml-0.5 h-5 w-5">
                <path d="M6 4.5v11l9-5.5-9-5.5Z" />
              </svg>
              <svg v-else viewBox="0 0 20 20" fill="currentColor" class="h-5 w-5">
                <path d="M6 4.5h3v11H6v-11Zm5 0h3v11h-3v-11Z" />
              </svg>
            </button>
            <div class="flex-1">
              <div
                class="h-1.5 cursor-pointer rounded-full bg-slate-300"
                @click="seek"
              >
                <div
                  class="h-full rounded-full bg-capture-500"
                  :style="{ width: `${progressPct}%` }"
                />
              </div>
              <div class="mt-1 flex justify-between font-mono text-xs text-ink-900/50">
                <span>{{ formatTime(currentTime) }}</span>
                <span>{{ formatTime(duration) }}</span>
              </div>
            </div>
          </div>

          <div class="mt-6 min-h-[7rem] border-t border-slate-300 pt-4">
            <p class="mb-2 font-mono text-xs uppercase tracking-wide text-ink-900/40">
              Transcripción (Groq Whisper)
            </p>
            <p v-if="!played" class="font-body text-sm text-ink-900/40">
              Dale a play para ver la transcripción real aparecer aquí.
            </p>
            <p v-else class="space-y-1 font-body text-sm leading-relaxed text-ink-900">
              <span
                v-for="(sentence, i) in TRANSCRIPT_SENTENCES"
                :key="i"
                :ref="(el) => setTranscriptRef(el, i)"
                class="block opacity-0"
              >{{ sentence }}</span>
            </p>
          </div>

          <div class="mt-6 space-y-2 border-t border-slate-300 pt-4 font-mono text-xs text-ink-900">
            <p
              v-for="(field, i) in FIELDS"
              :key="field.label"
              :ref="(el) => setFieldRef(el, i)"
              class="opacity-0"
            >
              <span class="text-ink-900/50">{{ field.label }}:</span> {{ field.value }}
            </p>
          </div>
        </div>

        <!-- Right: real generated document -->
        <div ref="documentCard" class="flex flex-col opacity-0">
          <p class="mb-2 font-mono text-xs uppercase tracking-wide text-ink-900/40">
            Documento generado
          </p>
          <div class="flex-1 overflow-hidden rounded-lg border border-slate-300">
            <iframe src="/demo/informe.pdf" title="Informe generado" class="h-full min-h-[320px] w-full" />
          </div>
          <div class="mt-4 flex items-center justify-between">
            <p class="font-mono text-xs text-ink-900/50">
              Generado con Claude Sonnet 5 · ${{ EXTRACTION_COST_USD.toFixed(6) }}
            </p>
            <a
              href="/demo/informe.pdf"
              download
              class="rounded-md bg-ink-900 px-4 py-2 font-body text-sm font-semibold text-white transition-transform hover:scale-[1.02]"
            >
              Descargar PDF
            </a>
          </div>
        </div>
      </div>
    </LandingRevealOnScroll>
  </section>
</template>
