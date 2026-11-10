<script setup lang="ts">
// The head of one sheet of the drawing set: the question it answers (the heading), its plain
// reading for anyone (no jargon), and its title block — sheet number and scale, as on a real
// drawing. The scale says how close the sheet looks: 1:1000 the whole system, 1:10 a detail.
withDefaults(defineProps<{ sheet: SheetKey; heading: string; plain: string; tone?: 'light' | 'dark' }>(), { tone: 'light' })

const { t } = useI18n()
</script>

<template>
  <header class="grid gap-6 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start lg:gap-12">
    <div class="max-w-[44rem]">
      <LandingSectionHeading :tone="tone" size="md">{{ heading }}</LandingSectionHeading>
      <p class="mb-0 mt-5 max-w-[38rem] font-body text-[1.0625rem] leading-relaxed" :class="tone === 'dark' ? 'text-white/80' : 'text-ink-900/80'">
        <span class="font-semibold" :class="tone === 'dark' ? 'text-white' : 'text-ink-900'">{{ t('landing.sheet.plain') }}.</span>
        {{ plain }}
      </p>
    </div>
    <!-- The title block: small, boxed and in the corner, like the one on a drawing. -->
    <dl
      class="m-0 grid w-fit grid-cols-[auto_auto] border font-mono text-[12px] leading-none lg:mt-2"
      :class="tone === 'dark' ? 'border-plano-line/40 text-white/75' : 'border-ink-900/25 text-ink-900/70'"
    >
      <dt class="border-b border-r px-2.5 py-2" :class="tone === 'dark' ? 'border-plano-line/40' : 'border-ink-900/25'">{{ t('landing.sheet.sheet') }}</dt>
      <dd class="m-0 border-b px-2.5 py-2 tabular-nums" :class="tone === 'dark' ? 'border-plano-line/40 text-white' : 'border-ink-900/25 text-ink-900'">
        {{ sheetNumber(sheet) }} / {{ SHEETS.length }}
      </dd>
      <dt class="border-r px-2.5 py-2" :class="tone === 'dark' ? 'border-plano-line/40' : 'border-ink-900/25'">{{ t('landing.sheet.scale') }}</dt>
      <dd class="m-0 px-2.5 py-2" :class="tone === 'dark' ? 'text-white' : 'text-ink-900'">{{ t(`landing.sheets.${sheet}.scale`) }}</dd>
    </dl>
  </header>
</template>
