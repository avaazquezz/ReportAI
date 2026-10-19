<script setup lang="ts">
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'

const { t } = useI18n()

// The page's second set-piece: the report's real path through the system. One datum (the
// "ficha") travels along a rail of five stages; each stage explains what happens, how, why it
// was built that way and what leaves the server. `active` is the single source of truth. On a
// desktop with room the scroll drives it (the scene is pinned); everywhere else it is a tablist.
const STAGES = ['dictate', 'transcribe', 'extract', 'approve', 'deliver'] as const
type Stage = (typeof STAGES)[number]
const LAST = STAGES.length - 1
const TECH = [0, 1, 2]
const WAVE = [6, 10, 14, 9, 16, 7, 12, 18, 8, 13, 10, 6]
const ICONS: Record<Stage, string> = {
  dictate: 'M12 3.5a2.75 2.75 0 0 0-2.75 2.75v5a2.75 2.75 0 0 0 5.5 0v-5A2.75 2.75 0 0 0 12 3.5ZM5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M9 21h6',
  transcribe: 'M3 12h1.5M7 8v8M11 4.5v15M15 8v8M19 10.5v3',
  extract: 'M9 4C7.2 4 7 5 7 6.5v2C7 10 6 11.5 4 12c2 .5 3 2 3 3.5v2C7 19 7.2 20 9 20M15 4c1.8 0 2 1 2 2.5v2c0 1.5 1 3 3 3.5-2 .5-3 2-3 3.5v2c0 1.5-.2 2.5-2 2.5',
  approve: 'M12 3l7 3v5.5c0 4.6-3 7.8-7 9.5-4-1.7-7-4.9-7-9.5V6l7-3ZM9 12l2.2 2.2L15.2 10',
  deliver: 'M7 3h7l4 4v14H7V3ZM14 3v4h4M10 12.5h5M10 16.5h5'
}
const EXTRACT_ROWS = ['deficiencia', 'empresa', 'medida', 'plazo'] as const
// Does anything leave the server at this stage? (The wording is in i18n: stages.<key>.data.)
const LEAVES: Record<Stage, boolean> = { dictate: true, transcribe: true, extract: true, approve: false, deliver: true }

const active = ref(0)
const pinned = ref(false)
// The stage visuals animate when the section comes into view, not at page load.
const seen = ref(false)
const root = ref<HTMLElement | null>(null)
const pinEl = ref<HTMLElement | null>(null)
const rail = ref<HTMLElement | null>(null)

let goTo: (i: number) => void = (i) => {
  active.value = i
}
const select = (i: number) => goTo(Math.min(Math.max(i, 0), LAST))

function onKey(e: KeyboardEvent) {
  const next: Record<string, number> = {
    ArrowRight: active.value + 1,
    ArrowDown: active.value + 1,
    ArrowLeft: active.value - 1,
    ArrowUp: active.value - 1,
    Home: 0,
    End: LAST
  }
  const target = next[e.key]
  if (target === undefined) return
  e.preventDefault()
  select(target)
  nextTick(() => document.getElementById(`arch-tab-${STAGES[Math.min(Math.max(target, 0), LAST)]}`)?.focus({ preventScroll: pinned.value }))
}

useMotionScope(
  root,
  (c, ctx) => {
    const railEl = rail.value!
    let alive = true
    const unpinned = () => {
      pinned.value = false
      goTo = (i) => {
        active.value = i
        gsap.to(railEl, { '--t': i, duration: c.motion ? 0.8 : 0, overwrite: true })
      }
    }
    gsap.set(railEl, { '--t': active.value })
    unpinned()

    if (c.reduce) seen.value = true
    else ScrollTrigger.create({ trigger: root.value, start: 'top 75%', once: true, onEnter: () => (seen.value = true) })

    if (c.motion && c.desktop) {
      // Only once the web fonts are in: until then the fallback face wraps differently, and the
      // scene's real height (which decides whether it fits the screen and can be pinned) is unknown.
      document.fonts.ready.then(() => {
        if (!alive || pinEl.value!.offsetHeight > window.innerHeight - 88) return
        ctx.add(() => {
          pinned.value = true
          active.value = 0
          const toRail = gsap.quickTo(railEl, '--t', { duration: 0.35, ease: 'power2.out' })
          const st = ScrollTrigger.create({
            trigger: pinEl.value,
            start: 'top top+=72',
            end: () => `+=${Math.round(window.innerHeight * 2.2)}`,
            pin: true,
            anticipatePin: 1,
            invalidateOnRefresh: true,
            snap: { snapTo: 1 / LAST, duration: { min: 0.15, max: 0.45 }, ease: 'power2.out' },
            onUpdate: (self) => {
              toRail(self.progress * LAST)
              const i = Math.round(self.progress * LAST)
              if (i !== active.value) active.value = i
            }
          })
          goTo = (i) => window.scrollTo({ top: st.start + (i / LAST) * (st.end - st.start), behavior: 'smooth' })
        })
      })
    }

    return () => {
      alive = false
      unpinned()
    }
  },
  { desktop: true }
)

const nodeClass = (i: number) =>
  i < active.value
    ? 'border-capture-500 bg-capture-600 text-white'
    : i === active.value
      ? 'scale-105 border-capture-500 bg-plano-950 text-capture-500 shadow-[0_0_0_6px_rgba(255,106,69,0.16)]'
      : 'border-plano-700 bg-plano-800 text-white/55 group-hover:border-plano-line group-hover:text-white'
</script>

<template>
  <section id="como-funciona" ref="root" class="grid-plano relative bg-plano-900 text-white">
    <div ref="pinEl" class="mx-auto max-w-[1240px] px-6 pb-6 pt-20 lg:pt-6">
      <header class="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between lg:gap-8">
        <LandingSectionHeading tone="dark" size="sm" class="lg:whitespace-nowrap">{{ t('landing.architecture.heading') }}</LandingSectionHeading>
        <p class="m-0 max-w-sm font-body text-[14px] leading-snug text-white/70">{{ t('landing.architecture.sub') }}</p>
      </header>

      <!-- Rail: five stages, the ficha rides above the one in play. --t is 0..4 (set by scroll or by a click). -->
      <div ref="rail" class="relative mt-6" style="--t: 0">
        <div class="pointer-events-none absolute left-[10%] right-[10%] top-[59px] h-px bg-plano-700" />
        <div class="pointer-events-none absolute left-[10%] top-[59px] h-px bg-capture-500" style="width: calc(var(--t) / 4 * 80%)" />
        <div class="pointer-events-none absolute top-0 z-10 -translate-x-1/2" style="left: clamp(54px, calc(10% + var(--t) / 4 * 80%), calc(100% - 54px))" aria-hidden="true">
          <div class="relative rounded border border-capture-500 bg-plano-950 px-2 py-0.5 font-mono text-[11px] whitespace-nowrap text-capture-500">
            <Transition name="ficha" mode="out-in">
              <span :key="active" class="block">{{ t(`landing.architecture.stages.${STAGES[active]}.artifact`) }}</span>
            </Transition>
            <span class="absolute -bottom-[5px] left-1/2 h-2 w-2 -translate-x-1/2 rotate-45 border-b border-r border-capture-500 bg-plano-950" />
          </div>
        </div>

        <ol role="tablist" :aria-label="t('landing.architecture.railLabel')" class="m-0 grid list-none grid-cols-5 p-0 pt-9" @keydown="onKey">
          <li v-for="(key, i) in STAGES" :key="key" role="presentation" class="flex justify-center">
            <button
              :id="`arch-tab-${key}`"
              type="button"
              role="tab"
              :aria-selected="i === active"
              :aria-controls="`arch-panel-${key}`"
              :tabindex="i === active ? 0 : -1"
              class="group flex cursor-pointer flex-col items-center border-0 bg-transparent p-0 text-center"
              @click="select(i)"
            >
              <span
                class="flex h-[46px] w-[46px] items-center justify-center rounded-full border transition-[transform,background-color,border-color,color,box-shadow] duration-500 ease-[cubic-bezier(0.22,0.8,0.12,1)]"
                :class="nodeClass(i)"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" class="h-[22px] w-[22px]" aria-hidden="true">
                  <path :d="ICONS[key]" />
                </svg>
              </span>
              <span class="mt-3 hidden font-plan text-[13px] font-bold leading-tight sm:block" :class="i === active ? 'text-white' : 'text-white/55'">
                {{ t(`landing.architecture.stages.${key}.name`) }}
              </span>
            </button>
          </li>
        </ol>
      </div>

      <!-- Panels: on desktop all five sit in one grid cell (the tallest sets the height, so nothing jumps
           and everything is in the DOM); below lg only the active one is shown. -->
      <div class="mt-6 lg:grid">
        <div
          v-for="(key, i) in STAGES"
          :id="`arch-panel-${key}`"
          :key="key"
          role="tabpanel"
          :aria-labelledby="`arch-tab-${key}`"
          class="stage-panel col-start-1 row-start-1 grid gap-8 transition-[opacity,transform] duration-500 ease-[cubic-bezier(0.22,0.8,0.12,1)] lg:grid-cols-[1.02fr_0.98fr] lg:gap-12"
          :class="i === active ? { 'is-on': seen } : 'hidden lg:invisible lg:grid lg:translate-y-2 lg:opacity-0'"
        >
          <div>
            <div class="flex items-baseline justify-between gap-4">
              <h3 class="m-0 font-plan text-[1.5rem] font-extrabold leading-tight tracking-[-0.03em]">{{ t(`landing.architecture.stages.${key}.name`) }}</h3>
              <p class="m-0 shrink-0 font-mono text-[11px] text-capture-500">{{ t('landing.architecture.stageOf', { n: i + 1, total: STAGES.length }) }}</p>
            </div>
            <p class="mb-0 mt-2 font-body text-[14.5px] leading-snug text-white/85">{{ t(`landing.architecture.stages.${key}.plain`) }}</p>
            <ul class="mb-0 mt-3 list-none space-y-1.5 pl-0 font-body text-[13px] leading-[1.42] text-white/70">
              <li v-for="n in TECH" :key="n" class="flex gap-2.5">
                <span class="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-plano-line" aria-hidden="true" />
                <span>{{ t(`landing.architecture.stages.${key}.tech[${n}]`) }}</span>
              </li>
            </ul>
            <div class="mt-3 border-l-2 border-capture-500 bg-plano-800/70 py-2 pl-4 pr-3">
              <p class="m-0 font-mono text-[11px] text-capture-500">{{ t('landing.architecture.whyLabel') }}</p>
              <p class="mb-0 mt-0.5 font-body text-[13px] leading-[1.42] text-white/90">{{ t(`landing.architecture.stages.${key}.why`) }}</p>
            </div>
          </div>

          <div class="flex flex-col">
            <div class="vcard rounded-xl border border-plano-700 bg-plano-800/80 p-4 font-mono text-[12.5px] leading-relaxed">
              <p class="m-0 text-[11px] text-plano-line">{{ t(`landing.architecture.visual.${key}.meta`) }}</p>

              <template v-if="key === 'dictate'">
                <div class="v-in ml-auto mt-4 flex w-fit items-center gap-2 rounded-2xl rounded-br-md bg-capture-600 px-3 py-2 text-white" style="--i: 0">
                  <svg viewBox="0 0 20 20" fill="currentColor" class="h-4 w-4 shrink-0" aria-hidden="true"><path d="M6 4.5v11l9-5.5-9-5.5Z" /></svg>
                  <span class="v-wave flex h-4 items-end gap-[3px]" aria-hidden="true">
                    <i v-for="(h, n) in WAVE" :key="n" class="block w-[2px] origin-bottom rounded-full bg-white/80" :style="{ height: `${h}px` }" />
                  </span>
                  <span class="text-[11px]">{{ t('landing.hero.stage.voiceDuration') }}</span>
                </div>
                <div class="v-in mx-auto my-3 h-6 w-px bg-plano-line/50" style="--i: 1" aria-hidden="true" />
                <div class="v-in rounded-lg border border-plano-700 bg-plano-950/60 p-3" style="--i: 2">
                  <p class="m-0 text-[11px] text-white/50">{{ t('landing.architecture.visual.dictate.job') }}</p>
                  <div class="mt-2 flex flex-wrap gap-2 text-[11.5px]">
                    <span class="rounded border border-plano-700 px-2 py-0.5 text-white/85">kind: <b class="font-medium text-capture-500">run</b></span>
                    <span class="rounded border border-plano-700 px-2 py-0.5 text-white/85">status: <b class="font-medium text-capture-500">queued</b></span>
                    <span class="rounded border border-plano-700 px-2 py-0.5 text-white/85">attempts: <b class="font-medium text-capture-500">0/3</b></span>
                  </div>
                </div>
                <p class="v-in mb-0 mt-3 text-[11.5px] text-plano-line" style="--i: 3">↳ {{ t('landing.architecture.visual.dictate.tx') }}</p>
              </template>

              <template v-else-if="key === 'transcribe'">
                <div class="v-in mt-4 flex h-8 items-end gap-[3px]" style="--i: 0" aria-hidden="true">
                  <i v-for="(h, n) in [...WAVE, ...WAVE, ...WAVE]" :key="n" class="block w-[3px] origin-bottom rounded-full bg-plano-line/60" :style="{ height: `${h + 6}px` }" />
                </div>
                <div class="v-in mx-auto my-3 h-5 w-px bg-plano-line/50" style="--i: 1" aria-hidden="true" />
                <p class="v-in m-0 rounded-lg border border-plano-700 bg-plano-950/60 p-3 text-[12.5px] leading-[1.7] text-white/80" style="--i: 2">
                  {{ t('landing.architecture.visual.transcribe.before') }}<mark class="v-mark rounded-sm px-0.5 text-white">{{ t('landing.architecture.visual.transcribe.mark') }}</mark>{{ t('landing.architecture.visual.transcribe.after') }}
                </p>
              </template>

              <template v-else-if="key === 'extract'">
                <div class="mt-3 rounded-lg border border-plano-700 bg-plano-950/60 p-3 text-[12px] leading-[1.6] text-white/80">
                  <div class="v-in text-white/50" style="--i: 0">{</div>
                  <div class="v-in pl-3" style="--i: 1">"deficiencias": [{</div>
                  <div v-for="(row, n) in EXTRACT_ROWS" :key="row" class="v-in pl-6" :style="{ '--i': n + 2 }">
                    <span class="text-plano-line">"{{ row }}"</span>: <span :class="row === 'plazo' ? 'text-capture-500' : 'text-white/90'">"{{ t(`landing.architecture.visual.extract.values.${row}`) }}"</span>
                  </div>
                  <div class="v-in pl-3" style="--i: 6">}]</div>
                  <div class="v-in text-white/50" style="--i: 6">}</div>
                </div>
                <p class="v-in mb-0 mt-3 text-[11.5px] text-white/60" style="--i: 7">
                  evidence ← <span class="text-white/90">"{{ t('landing.architecture.visual.extract.quote') }}"</span>
                </p>
                <p class="v-in mb-0 mt-1.5 text-[11.5px] text-[#5FD3A6]" style="--i: 8">✓ {{ t('landing.architecture.visual.extract.verified') }}</p>
                <p class="v-in mb-0 mt-1 text-[11.5px] text-[#5FD3A6]" style="--i: 9">✓ {{ t('landing.architecture.visual.extract.valid') }}</p>
              </template>

              <template v-else-if="key === 'approve'">
                <div class="v-in mt-4 max-w-[19rem] rounded-2xl rounded-bl-md bg-surface-0 px-4 py-3 font-body text-[13px] leading-snug text-ink-900" style="--i: 0">
                  <p class="m-0 font-medium">{{ t('landing.architecture.visual.approve.header') }}</p>
                  <p class="mb-0 mt-2 font-mono text-[11.5px] leading-relaxed text-ink-900/80">
                    {{ t('landing.architecture.visual.approve.site') }}<br>{{ t('landing.architecture.visual.approve.date') }}<br>{{ t('landing.architecture.visual.approve.issues') }}
                  </p>
                </div>
                <div class="mt-3 flex max-w-[19rem] flex-wrap gap-2 font-body text-[12px]">
                  <span class="v-in rounded-md border border-approved-600 bg-surface-0 px-2.5 py-1 font-medium text-approved-600" style="--i: 2">{{ t('landing.architecture.visual.approve.confirm') }}</span>
                  <span class="v-in rounded-md border border-white/25 px-2.5 py-1 text-white/80" style="--i: 3">{{ t('landing.architecture.visual.approve.correct') }}</span>
                  <span class="v-in rounded-md border border-white/25 px-2.5 py-1 text-white/80" style="--i: 4">{{ t('landing.architecture.visual.approve.cancel') }}</span>
                </div>
                <p class="v-in mb-0 mt-5 flex items-center gap-2 text-[11.5px] text-capture-500" style="--i: 6">
                  <span class="v-pulse h-2 w-2 rounded-full bg-capture-500" aria-hidden="true" />{{ t('landing.architecture.visual.approve.paused') }}
                </p>
              </template>

              <template v-else>
                <div class="mt-4 flex flex-wrap items-center gap-x-2 gap-y-2 text-[11.5px]">
                  <span class="v-in rounded border border-plano-700 px-2 py-1 text-white/85" style="--i: 0">{{ t('landing.architecture.visual.deliver.template') }}</span>
                  <span class="v-in text-capture-500" style="--i: 1">→ docxtpl →</span>
                  <span class="v-in rounded border border-plano-700 px-2 py-1 text-white/85" style="--i: 2">{{ t('landing.architecture.visual.deliver.filled') }}</span>
                  <span class="v-in text-capture-500" style="--i: 3">→ Gotenberg →</span>
                  <span class="v-in rounded border border-capture-500 px-2 py-1 text-capture-500" style="--i: 4">{{ t('landing.architecture.visual.deliver.pdf') }}</span>
                </div>
                <ul class="mb-0 mt-5 list-none space-y-2 pl-0 text-[12px]">
                  <li v-for="(copy, n) in ['telegram', 'email1', 'email2']" :key="copy" class="v-in flex items-center gap-2 text-white/85" :style="{ '--i': n + 6 }">
                    <svg viewBox="0 0 20 20" fill="none" stroke="#5FD3A6" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" class="h-3.5 w-3.5 shrink-0" aria-hidden="true"><path d="M4 10.5l4 4 8-9" /></svg>
                    {{ t(`landing.architecture.visual.deliver.${copy}`) }}
                  </li>
                </ul>
              </template>
            </div>

            <p class="mb-0 mt-2.5 flex items-start gap-2.5 font-body text-[12.5px] leading-snug" :class="LEAVES[key] ? 'text-white/75' : 'text-[#5FD3A6]'">
              <span class="mt-0.5 shrink-0 font-mono text-[11px] text-white/45">{{ t('landing.architecture.dataLabel') }}</span>
              <span>{{ t(`landing.architecture.stages.${key}.data`) }}</span>
            </p>
          </div>
        </div>
      </div>

      <div class="mt-4 flex items-center justify-between gap-4">
        <p class="m-0 font-mono text-[11px] text-white/45">{{ pinned ? t('landing.architecture.hintPinned') : t('landing.architecture.hintTabs') }}</p>
        <div class="flex gap-2">
          <button
            type="button"
            class="cursor-pointer rounded-md border border-plano-700 bg-transparent px-3 py-1.5 font-body text-[13px] text-white/80 transition-colors enabled:hover:border-plano-line enabled:hover:text-white disabled:cursor-default disabled:opacity-35"
            :disabled="active === 0"
            @click="select(active - 1)"
          >
            ← {{ t('landing.architecture.prev') }}
          </button>
          <button
            type="button"
            class="cursor-pointer rounded-md border border-capture-500 bg-transparent px-3 py-1.5 font-body text-[13px] text-capture-500 transition-colors enabled:hover:bg-capture-500 enabled:hover:text-plano-950 disabled:cursor-default disabled:opacity-35"
            :disabled="active === LAST"
            @click="select(active + 1)"
          >
            {{ t('landing.architecture.next') }} →
          </button>
        </div>
      </div>
    </div>

    <LandingArchitectureTopology />
  </section>
</template>

<style scoped>
/* The stage visuals replay every time their panel turns on: the animation only exists under .is-on. */
.v-in {
  opacity: 0;
}
.is-on .v-in {
  animation: v-in 0.55s var(--ease-ra) both;
  animation-delay: calc(var(--i, 0) * 110ms + 150ms);
}
@keyframes v-in {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}
.v-wave i {
  transform: scaleY(0.4);
}
.is-on .v-wave i {
  animation: v-wave 0.5s ease-in-out 5 alternate;
}
@keyframes v-wave {
  to {
    transform: scaleY(1);
  }
}
.v-mark {
  background-image: linear-gradient(rgb(255 106 69 / 0.35), rgb(255 106 69 / 0.35));
  background-repeat: no-repeat;
  background-size: 0 100%;
}
.is-on .v-mark {
  animation: v-mark 0.7s var(--ease-ra) 1.1s forwards;
}
@keyframes v-mark {
  to {
    background-size: 100% 100%;
  }
}
.is-on .v-pulse {
  animation: v-pulse 1.1s ease-in-out 4;
}
@keyframes v-pulse {
  50% {
    opacity: 0.25;
  }
}

.ficha-enter-active,
.ficha-leave-active {
  transition:
    opacity 0.18s,
    transform 0.18s;
}
.ficha-enter-from {
  opacity: 0;
  transform: translateY(4px);
}
.ficha-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
