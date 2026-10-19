<script setup lang="ts">
import gsap from 'gsap'

const { t } = useI18n()

// What a company's installation is made of (infra/install/docker-compose.yml) and the four
// things that talk to the outside. Click a piece to read what it does; the toggle dims the
// inside so only what leaves the server stays lit.
const LEFT = ['telegram', 'smtp'] as const
const RIGHT = ['voice', 'model'] as const
const INSIDE = ['caddy', 'frontend', 'backend', 'worker', 'postgres', 'gotenberg', 'storage', 'keys'] as const
// Which way data moves on each link: the dot travels from the server out ('r' = to the right).
const DIRECTION = { telegram: 'l', smtp: 'l', voice: 'r', model: 'r' } as const

const selected = ref<string | null>(null)
const onlyOutside = ref(false)
const flowing = ref(false)
const root = ref<HTMLElement | null>(null)

const caption = computed(() => {
  if (!selected.value) return null
  const [side, key] = selected.value.split('.') as ['inside' | 'outside', string]
  const base = `landing.architecture.topology.${side}.${key}`
  return {
    name: t(`${base}.name`),
    role: t(`${base}.role`),
    body: t(`${base}.body`),
    detail: side === 'outside' ? t(`${base}.sends`) : t('landing.architecture.topology.stays'),
    leaves: side === 'outside'
  }
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
  gsap.from('.tile', {
    opacity: 0,
    y: 14,
    duration: 0.6,
    stagger: 0.05,
    clearProps: 'opacity,transform',
    scrollTrigger: { trigger: '.frame', start: 'top 80%', once: true, onEnter: () => (flowing.value = true) }
  })
  gsap.from('.out-node', {
    opacity: 0,
    x: (i: number) => (i < 2 ? -16 : 16),
    duration: 0.7,
    stagger: 0.08,
    clearProps: 'opacity,transform',
    scrollTrigger: { trigger: '.frame', start: 'top 80%', once: true }
  })
})
</script>

<template>
  <div ref="root" class="mx-auto max-w-[1240px] border-t border-plano-700/70 px-6 pb-24 pt-16 md:pt-20">
    <div class="flex flex-col gap-4 md:flex-row md:items-end md:justify-between md:gap-10">
      <div class="max-w-2xl">
        <LandingSectionHeading tone="dark" size="md" as="h3">{{ t('landing.architecture.topology.heading') }}</LandingSectionHeading>
        <p class="mb-0 mt-4 font-body text-[15px] leading-relaxed text-white/70">{{ t('landing.architecture.topology.sub') }}</p>
      </div>
      <button
        type="button"
        :aria-pressed="onlyOutside"
        class="inline-flex shrink-0 cursor-pointer items-center gap-2.5 self-start rounded-md border bg-transparent px-3.5 py-2 font-body text-[13px] transition-colors md:self-auto"
        :class="onlyOutside ? 'border-capture-500 text-capture-500' : 'border-plano-700 text-white/80 hover:border-plano-line hover:text-white'"
        @click="onlyOutside = !onlyOutside; flowing = true"
      >
        <span class="relative h-4 w-7 rounded-full transition-colors" :class="onlyOutside ? 'bg-capture-500' : 'bg-plano-700'" aria-hidden="true">
          <span class="absolute top-0.5 h-3 w-3 rounded-full bg-white transition-[left]" :class="onlyOutside ? 'left-[14px]' : 'left-0.5'" />
        </span>
        {{ onlyOutside ? t('landing.architecture.topology.toggleOff') : t('landing.architecture.topology.toggleOn') }}
      </button>
    </div>

    <div class="mt-12 grid gap-y-3 lg:grid-cols-[minmax(0,14rem)_4rem_minmax(0,1fr)_4rem_minmax(0,14rem)] lg:grid-rows-2 lg:gap-y-5" :class="{ 'is-flowing': flowing }">
      <template v-for="(key, i) in LEFT" :key="key">
        <button
          type="button"
          class="out-node cursor-pointer rounded-xl border bg-plano-800/70 p-4 text-left transition-[border-color,box-shadow,background-color] duration-300 lg:col-start-1"
          :class="[i === 0 ? 'lg:row-start-1' : 'lg:row-start-2', selected === `outside.${key}` || onlyOutside ? 'border-capture-500' : 'border-plano-700 hover:border-plano-line', selected === `outside.${key}` ? 'shadow-[0_0_0_4px_rgba(255,106,69,0.14)]' : '']"
          :aria-pressed="selected === `outside.${key}`"
          @click="pick(`outside.${key}`)"
        >
          <span class="block font-mono text-[10.5px] text-capture-500">{{ t(`landing.architecture.topology.outside.${key}.role`) }}</span>
          <span class="mt-1 block font-plan text-[15px] font-bold leading-tight text-white">{{ t(`landing.architecture.topology.outside.${key}.name`) }}</span>
          <span class="mt-1.5 block font-body text-[12.5px] leading-snug text-white/65">{{ t(`landing.architecture.topology.outside.${key}.body`) }}</span>
        </button>
        <span class="link relative hidden self-center lg:col-start-2 lg:block" :class="i === 0 ? 'lg:row-start-1' : 'lg:row-start-2'" aria-hidden="true">
          <span class="block h-px w-full border-t border-dashed" :class="onlyOutside ? 'border-capture-500' : 'border-plano-line/50'" />
          <i class="dot dot-l absolute -top-[3px] h-[7px] w-[7px] rounded-full bg-capture-500" />
        </span>
      </template>

      <div
        class="frame relative mt-6 rounded-2xl border border-dashed border-plano-line/60 bg-plano-950/40 p-4 pt-7 lg:col-start-3 lg:row-span-2 lg:row-start-1 lg:mt-0"
      >
        <p class="absolute -top-3 left-4 m-0 bg-plano-900 px-2 font-mono text-[11px] text-plano-line">
          {{ t('landing.architecture.topology.insideLabel') }} · <span class="text-white/55">{{ t('landing.architecture.topology.insideHint') }}</span>
        </p>
        <div class="grid h-full grid-cols-2 content-center gap-2.5 sm:grid-cols-4">
          <button
            v-for="key in INSIDE"
            :key="key"
            type="button"
            class="tile cursor-pointer rounded-lg border bg-plano-800/80 p-3 text-left transition-[border-color,box-shadow] duration-300"
            :class="selected === `inside.${key}` ? 'border-plano-line shadow-[0_0_0_4px_rgba(143,176,227,0.14)]' : 'border-plano-700 hover:border-plano-line'"
            :aria-pressed="selected === `inside.${key}`"
            @click="pick(`inside.${key}`)"
          >
            <span class="block transition-opacity duration-300" :class="onlyOutside ? 'opacity-30' : ''">
              <span class="block font-plan text-[13.5px] font-bold leading-tight text-white">{{ t(`landing.architecture.topology.inside.${key}.name`) }}</span>
              <span class="mt-1 block font-mono text-[10.5px] text-plano-line">{{ t(`landing.architecture.topology.inside.${key}.role`) }}</span>
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
          <span class="block font-mono text-[10.5px] text-capture-500">{{ t(`landing.architecture.topology.outside.${key}.role`) }}</span>
          <span class="mt-1 block font-plan text-[15px] font-bold leading-tight text-white">{{ t(`landing.architecture.topology.outside.${key}.name`) }}</span>
          <span class="mt-1.5 block font-body text-[12.5px] leading-snug text-white/65">{{ t(`landing.architecture.topology.outside.${key}.body`) }}</span>
        </button>
      </template>
    </div>

    <div class="mt-8 min-h-[4.5rem] rounded-xl border border-plano-700 bg-plano-800/50 px-5 py-4" role="status" aria-live="polite">
      <p v-if="!caption" class="m-0 font-body text-[14px] text-white/55">{{ t('landing.architecture.topology.captionHint') }}</p>
      <template v-else>
        <p class="m-0 flex flex-wrap items-baseline gap-x-3 font-body text-[14px] text-white/80">
          <b class="font-plan text-[15px] font-bold text-white">{{ caption.name }}</b>
          <span class="font-mono text-[11px] text-plano-line">{{ caption.role }}</span>
        </p>
        <p class="mb-0 mt-1.5 font-body text-[14px] leading-snug text-white/75">{{ caption.body }}</p>
        <p class="mb-0 mt-2 font-body text-[13.5px] leading-snug" :class="caption.leaves ? 'text-capture-500' : 'text-[#5FD3A6]'">
          <span class="font-mono text-[11px] text-white/55">{{ caption.leaves ? t('landing.architecture.topology.sends') : '' }}</span>
          {{ caption.leaves ? '' : '✓ ' }}{{ caption.detail }}
        </p>
      </template>
    </div>
  </div>
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
