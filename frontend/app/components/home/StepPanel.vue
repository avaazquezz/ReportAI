<script setup lang="ts">
// The sheet as it looks at each step: the capture screen while dictating, the draft with its
// evidence and a missing field, then approved and sent.
defineProps<{ step: 'dictate' | 'review' | 'sign' }>()
const { t } = useI18n()
const LEVEL = [10, 16, 24, 14, 20, 9, 18, 26, 12, 8, 17, 22, 11, 15, 19]
</script>

<template>
  <div class="relative">
    <!-- Dictating: the app's own capture screen. -->
    <div v-if="step === 'dictate'" class="sheet mx-auto w-full max-w-[19rem] rounded-[1.6rem] border-[6px] border-ink-900 px-5 pb-8 pt-6">
      <p class="m-0 text-[1.05rem] font-semibold">{{ t('home.steps.panel.newReport') }}</p>
      <p class="m-0 mt-1 text-[0.8rem] text-ink-900/60">{{ t('home.steps.panel.reportType') }}</p>
      <div class="mt-10 grid place-items-center">
        <span class="grid h-24 w-24 place-items-center rounded-full bg-[#C0432A] text-white shadow-[0_0_0_10px_rgb(192_67_42/0.12)]" aria-hidden="true">
          <svg viewBox="0 0 24 24" class="h-9 w-9"><rect x="9" y="3" width="6" height="11" rx="3" fill="currentColor" /><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" /></svg>
        </span>
        <p class="m-0 mt-5 text-[0.85rem] font-semibold text-[#C0432A]">{{ t('home.steps.panel.recording') }} · <span class="t-data">0:42</span></p>
        <span class="mt-4 flex h-7 items-center gap-[3px]" aria-hidden="true">
          <i v-for="(h, i) in LEVEL" :key="i" class="block w-[3px] rounded-full bg-ink-900/60" :style="{ height: `${h}px` }" />
        </span>
      </div>
    </div>

    <!-- The draft: every value with its sentence, and what's missing marked in red. -->
    <div v-else-if="step === 'review'" class="sheet rounded-[2px] px-7 pb-8 pt-6">
      <p class="m-0 text-[0.75rem] font-semibold text-ink-900/60">{{ t('home.hero.sheet.fields.deficiency') }}</p>
      <p class="field-rule is-filled m-0 mt-1 pb-1.5 text-[0.95rem]">{{ t('home.hero.sheet.values.deficiency') }}</p>
      <p class="m-0 mt-2 border-l-2 border-ink-900/15 pl-3 text-[0.82rem] text-ink-900/60">{{ t('home.steps.panel.evidence') }}</p>
      <p class="m-0 mt-6 text-[0.75rem] font-semibold text-ink-900/60">{{ t('home.hero.sheet.fields.company') }}</p>
      <p class="field-rule is-filled m-0 mt-1 pb-1.5 text-[0.95rem]">{{ t('home.hero.sheet.values.company') }}</p>
      <p class="m-0 mt-6 text-[0.75rem] font-semibold text-ink-900/60">{{ t('home.hero.sheet.fields.deadline') }}</p>
      <p class="field-rule m-0 mt-1 min-h-[1.9rem] pb-1.5 text-[0.85rem] font-semibold text-[#C0432A]">{{ t('home.review.marginNote') }}</p>
    </div>

    <!-- Approved and sent. -->
    <div v-else class="sheet relative rounded-[2px] px-7 pb-8 pt-6">
      <p class="m-0 text-[0.75rem] font-semibold text-ink-900/60">{{ t('home.hero.sheet.fields.deadline') }}</p>
      <p class="field-rule is-filled m-0 mt-1 pb-1.5 text-[0.95rem]">{{ t('home.hero.sheet.values.deadline') }}</p>
      <p class="m-0 mt-6 text-[0.75rem] font-semibold text-ink-900/60">{{ t('home.hero.sheet.fields.measure') }}</p>
      <p class="field-rule is-filled m-0 mt-1 pb-1.5 text-[0.95rem]">{{ t('home.hero.sheet.values.measure') }}</p>
      <HomeStamp class="absolute right-6 top-6" :label="t('home.review.stamp')" />
      <p class="m-0 mt-8 text-[0.85rem] text-ink-900/70">{{ t('home.steps.panel.approvedBy') }}</p>
      <p class="t-data m-0 mt-1 text-ink-900/60">{{ t('home.steps.panel.sent') }}</p>
    </div>
  </div>
</template>
