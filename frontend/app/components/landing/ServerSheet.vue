<script setup lang="ts">
import gsap from 'gsap'

// Sheet 2, the server at 1:100: the containers of an installation (infra/docker-compose.prod.yml
// hosted, infra/install/docker-compose.yml self-hosted) and the four things that talk to the
// outside. The mode switch shows the point of the sheet: only the way in changes (Traefik or
// Caddy); everything else is the same code. Click a piece to read what it does; the toggle dims
// the inside so only what leaves the server stays lit.
const { t } = useI18n()

const LEFT = ['chats', 'smtp'] as const
const RIGHT = ['voice', 'model'] as const
const INSIDE = ['proxy', 'frontend', 'backend', 'worker', 'postgres', 'gotenberg', 'storage', 'keys'] as const
// Which way data moves on each link: the dot travels from the server out ('r' = to the right).
const DIRECTION = { chats: 'l', smtp: 'l', voice: 'r', model: 'r' } as const
const MODES = ['saas', 'self'] as const
type Mode = (typeof MODES)[number]

const mode = ref<Mode>('saas')
const selected = ref<string | null>(null)
const onlyOutside = ref(false)
const flowing = ref(false)
const root = ref<HTMLElement | null>(null)

const base = 'landing.architecture.topology'
// The way in is the one piece that differs between the two modes.
const insideName = (key: string) => (key === 'proxy' ? t(`${base}.inside.proxy.${mode.value === 'saas' ? 'nameSaas' : 'nameSelf'}`) : t(`${base}.inside.${key}.name`))
const insideBody = (key: string) => (key === 'proxy' ? t(`${base}.inside.proxy.${mode.value === 'saas' ? 'bodySaas' : 'bodySelf'}`) : t(`${base}.inside.${key}.body`))

const caption = computed(() => {
  if (!selected.value) return null
  const [side, key] = selected.value.split('.') as ['inside' | 'outside', string]
  return side === 'outside'
    ? { name: t(`${base}.outside.${key}.name`), role: t(`${base}.outside.${key}.role`), body: t(`${base}.outside.${key}.body`), detail: t(`${base}.outside.${key}.sends`), leaves: true }
    : { name: insideName(key), role: t(`${base}.inside.${key}.role`), body: insideBody(key), detail: t(`${base}.stays`), leaves: false }
})
const pick = (id: string) => {
  selected.value = selected.value === id ? null : id
  flowing.value = true
}

useMotionScope(root, (c) => {
  if (c.reduce) {
    flowing.value = true
    return
  }
  const scrollTrigger = { trigger: '.frame', start: 'top 80%', once: true }
  gsap.from('.tile', { opacity: 0, y: 14, duration: 0.6, stagger: 0.05, clearProps: 'opacity,transform', scrollTrigger: { ...scrollTrigger, onEnter: () => (flowing.value = true) } })
  gsap.from('.out-node', { opacity: 0, x: (i: number) => (i < 2 ? -16 : 16), duration: 0.7, stagger: 0.08, clearProps: 'opacity,transform', scrollTrigger })
})
</script>

<template>
  <section :id="SHEET_IDS.server" ref="root" class="grid-plano scroll-mt-20 bg-plano-900 text-white" data-tone="dark">
    <div class="mx-auto max-w-[1240px] px-6 py-20 lg:py-28">
      <LandingSheetHead sheet="server" tone="dark" :heading="t(`${base}.heading`)" :plain="t(`${base}.sub`)" />

      <div class="mt-12 flex flex-wrap items-center justify-between gap-4">
        <div class="inline-flex rounded-md border border-plano-700 p-1" role="group" :aria-label="t(`${base}.modeLabel`)">
          <button
            v-for="m in MODES"
            :key="m"
            type="button"
            :aria-pressed="mode === m"
            class="cursor-pointer rounded border-0 px-3.5 py-1.5 font-body text-[13px] transition-colors"
            :class="mode === m ? 'bg-white text-plano-950' : 'bg-transparent text-white/75 hover:text-white'"
            @click="mode = m"
          >
            {{ t(`${base}.modes.${m}`) }}
          </button>
        </div>
        <button
          type="button"
          :aria-pressed="onlyOutside"
          class="inline-flex cursor-pointer items-center gap-2.5 rounded-md border bg-transparent px-3.5 py-2 font-body text-[13px] transition-colors"
          :class="onlyOutside ? 'border-capture-500 text-capture-500' : 'border-plano-700 text-white/80 hover:border-plano-line hover:text-white'"
          @click="onlyOutside = !onlyOutside; flowing = true"
        >
          <span class="relative h-4 w-7 rounded-full transition-colors" :class="onlyOutside ? 'bg-capture-500' : 'bg-plano-700'" aria-hidden="true">
            <span class="absolute top-0.5 h-3 w-3 rounded-full bg-white transition-[left]" :class="onlyOutside ? 'left-[14px]' : 'left-0.5'" />
          </span>
          {{ onlyOutside ? t(`${base}.toggleOff`) : t(`${base}.toggleOn`) }}
        </button>
      </div>

      <div class="mt-10 grid gap-y-3 lg:grid-cols-[minmax(0,14rem)_4rem_minmax(0,1fr)_4rem_minmax(0,14rem)] lg:grid-rows-2 lg:gap-y-5" :class="{ 'is-flowing': flowing }">
        <template v-for="(key, i) in LEFT" :key="key">
          <button
            type="button"
            class="out-node cursor-pointer rounded-xl border bg-plano-800/70 p-4 text-left transition-[border-color,box-shadow,background-color] duration-300 lg:col-start-1"
            :class="[i === 0 ? 'lg:row-start-1' : 'lg:row-start-2', selected === `outside.${key}` || onlyOutside ? 'border-capture-500' : 'border-plano-700 hover:border-plano-line', selected === `outside.${key}` ? 'shadow-[0_0_0_4px_rgba(255,106,69,0.14)]' : '']"
            :aria-pressed="selected === `outside.${key}`"
            @click="pick(`outside.${key}`)"
          >
            <span class="block font-mono text-[11.5px] text-capture-500">{{ t(`${base}.outside.${key}.role`) }}</span>
            <span class="mt-1 block font-plan text-[15px] font-bold leading-tight text-white">{{ t(`${base}.outside.${key}.name`) }}</span>
            <span class="mt-1.5 block font-body text-[12.5px] leading-snug text-white/70">{{ t(`${base}.outside.${key}.body`) }}</span>
          </button>
          <span class="link relative hidden self-center lg:col-start-2 lg:block" :class="i === 0 ? 'lg:row-start-1' : 'lg:row-start-2'" aria-hidden="true">
            <span class="block h-px w-full border-t border-dashed" :class="onlyOutside ? 'border-capture-500' : 'border-plano-line/50'" />
            <i class="dot dot-l absolute -top-[3px] h-[7px] w-[7px] rounded-full bg-capture-500" />
          </span>
        </template>

        <div class="frame relative mt-6 rounded-2xl border border-dashed border-plano-line/60 bg-plano-950/40 p-4 pt-7 lg:col-start-3 lg:row-span-2 lg:row-start-1 lg:mt-0">
          <p class="absolute -top-3 left-4 m-0 bg-plano-900 px-2 font-mono text-[12px] text-plano-line">
            {{ mode === 'saas' ? t(`${base}.insideLabelSaas`) : t(`${base}.insideLabel`) }} ·
            <span class="text-white/60">{{ mode === 'saas' ? t(`${base}.insideHintSaas`) : t(`${base}.insideHint`) }}</span>
          </p>
          <div class="grid h-full grid-cols-2 content-center gap-2.5 sm:grid-cols-4">
            <button
              v-for="key in INSIDE"
              :key="key"
              type="button"
              class="tile cursor-pointer rounded-lg border bg-plano-800/80 p-3 text-left transition-[border-color,box-shadow] duration-300"
              :class="selected === `inside.${key}` ? 'border-plano-line shadow-[0_0_0_4px_rgba(143,176,227,0.14)]' : key === 'proxy' ? 'border-plano-line/70 hover:border-plano-line' : 'border-plano-700 hover:border-plano-line'"
              :aria-pressed="selected === `inside.${key}`"
              @click="pick(`inside.${key}`)"
            >
              <span class="block transition-opacity duration-300" :class="onlyOutside ? 'opacity-30' : ''">
                <span class="block font-plan text-[13.5px] font-bold leading-tight text-white">{{ insideName(key) }}</span>
                <span class="mt-1 block font-mono text-[11.5px] text-plano-line">{{ t(`${base}.inside.${key}.role`) }}</span>
              </span>
            </button>
          </div>
        </div>

        <template v-for="(key, i) in RIGHT" :key="key">
          <span class="link relative hidden self-center lg:col-start-4 lg:block" :class="i === 0 ? 'lg:row-start-1' : 'lg:row-start-2'" aria-hidden="true">
            <span class="block h-px w-full border-t border-dashed" :class="onlyOutside ? 'border-capture-500' : 'border-plano-line/50'" />
            <i class="dot absolute -top-[3px] h-[7px] w-[7px] rounded-full bg-capture-500" :class="DIRECTION[key] === 'r' ? 'dot-r' : 'dot-l'" />
          </span>
          <button
            type="button"
            class="out-node mt-3 cursor-pointer rounded-xl border bg-plano-800/70 p-4 text-left transition-[border-color,box-shadow,background-color] duration-300 first:mt-6 lg:col-start-5 lg:mt-0 lg:first:mt-0"
            :class="[i === 0 ? 'lg:row-start-1' : 'lg:row-start-2', selected === `outside.${key}` || onlyOutside ? 'border-capture-500' : 'border-plano-700 hover:border-plano-line', selected === `outside.${key}` ? 'shadow-[0_0_0_4px_rgba(255,106,69,0.14)]' : '']"
            :aria-pressed="selected === `outside.${key}`"
            @click="pick(`outside.${key}`)"
          >
            <span class="block font-mono text-[11.5px] text-capture-500">{{ t(`${base}.outside.${key}.role`) }}</span>
            <span class="mt-1 block font-plan text-[15px] font-bold leading-tight text-white">{{ t(`${base}.outside.${key}.name`) }}</span>
            <span class="mt-1.5 block font-body text-[12.5px] leading-snug text-white/70">{{ t(`${base}.outside.${key}.body`) }}</span>
          </button>
        </template>
      </div>

      <div class="mt-8 min-h-[4.5rem] rounded-xl border border-plano-700 bg-plano-800/50 px-5 py-4" role="status" aria-live="polite">
        <p v-if="!caption" class="m-0 font-body text-[14px] text-white/60">{{ t(`${base}.captionHint`) }}</p>
        <template v-else>
          <p class="m-0 flex flex-wrap items-baseline gap-x-3 font-body text-[14px] text-white/80">
            <b class="font-plan text-[15px] font-bold text-white">{{ caption.name }}</b>
            <span class="font-mono text-[12px] text-plano-line">{{ caption.role }}</span>
          </p>
          <p class="mb-0 mt-1.5 font-body text-[14px] leading-snug text-white/80">{{ caption.body }}</p>
          <p class="mb-0 mt-2 font-body text-[13.5px] leading-snug" :class="caption.leaves ? 'text-capture-500' : 'text-[#5FD3A6]'">
            <span v-if="caption.leaves" class="font-mono text-[12px] text-white/60">{{ t(`${base}.sends`) }} </span>
            <span v-else aria-hidden="true">✓ </span>{{ caption.detail }}
          </p>
        </template>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* Data moving along a link: a few passes when the diagram comes into view or is touched, then still. */
.dot {
  opacity: 0;
  left: 0;
}
.is-flowing .dot-r {
  animation: flow-r 1.8s var(--ease-ra) 3;
}
.is-flowing .dot-l {
  animation: flow-l 1.8s var(--ease-ra) 3;
}
@keyframes flow-r {
  0% {
    left: 0;
    opacity: 1;
  }
  100% {
    left: calc(100% - 7px);
    opacity: 1;
  }
}
@keyframes flow-l {
  0% {
    left: calc(100% - 7px);
    opacity: 1;
  }
  100% {
    left: 0;
    opacity: 1;
  }
}
</style>
