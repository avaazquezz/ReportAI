<script setup lang="ts">
// "Your Word file, not ours": the same page twice, as ReportAI reads it (its tags) and as the
// client receives it (the values). A quiet comparison between two of the page's set-pieces.
const { t } = useI18n()
const FIELDS = ['site', 'date', 'company'] as const
const TABLE = ['deficiency', 'measure', 'deadline'] as const
// Built here: a literal "{{" inside a template mustache would read as a nested interpolation.
const tagOf = (key: string) => `{{ ${t(`home.hero.sheet.tags.${key}`)} }}`
</script>

<template>
  <section class="space-l border-t border-ink-900/10" aria-labelledby="template-title">
    <div class="home-grid gap-y-12">
      <div class="col-span-12 lg:col-span-5">
        <h2 id="template-title" class="t-section m-0">{{ t('home.template.heading') }}</h2>
        <p class="t-lead m-0 mt-8 text-ink-900/80">{{ t('home.template.body') }}</p>
        <p class="t-body m-0 mt-6 text-ink-900/60">{{ t('home.template.starters') }}</p>
      </div>

      <div class="col-span-12 grid gap-6 sm:grid-cols-2 lg:col-span-7 lg:mt-24">
        <figure v-for="side in ['tags', 'values']" :key="side" class="m-0">
          <figcaption class="mb-3 text-[0.82rem] font-semibold text-ink-900/60">
            {{ side === 'tags' ? t('home.template.tagCaption') : t('home.template.valueCaption') }}
          </figcaption>
          <div class="sheet rounded-[2px] px-6 pb-8 pt-6 text-[0.8rem]" :class="side === 'tags' ? 'rotate-[-0.6deg]' : 'rotate-[0.4deg]'">
            <div class="flex items-center justify-between border-b border-ink-900/10 pb-4">
              <span class="grid h-8 w-8 place-items-center rounded-[2px] bg-doc-700 text-[0.6rem] font-semibold text-white" aria-hidden="true">{{ t('home.hero.sheet.mark') }}</span>
              <span class="t-data text-[0.7rem] text-ink-900/60">{{ side === 'tags' ? t('home.template.file') : 'PDF' }}</span>
            </div>
            <p class="m-0 mt-4 text-center text-[0.78rem] font-semibold uppercase tracking-[0.03em] text-doc-700">{{ t('home.hero.sheet.title') }}</p>
            <dl class="m-0 mt-4 grid gap-1.5">
              <div v-for="key in FIELDS" :key="key" class="flex gap-1.5">
                <dt class="shrink-0 font-semibold">{{ t(`home.hero.sheet.fields.${key}`) }}:</dt>
                <dd class="m-0 min-w-0">
                  <span v-if="side === 'tags'" class="t-data rounded-[2px] bg-[#C0432A]/5 px-1 text-[0.72rem] text-[#C0432A]">{{ tagOf(key) }}</span>
                  <span v-else>{{ t(`home.hero.sheet.values.${key}`) }}</span>
                </dd>
              </div>
            </dl>
            <table class="mt-5 w-full border-collapse text-left text-[0.78rem]">
              <thead>
                <tr class="bg-doc-700 text-white">
                  <th v-for="key in TABLE" :key="key" class="px-1.5 py-1 font-semibold">{{ t(`home.hero.sheet.fields.${key}`) }}</th>
                </tr>
              </thead>
              <tbody>
                <tr class="align-top">
                  <td v-for="key in TABLE" :key="key" class="border border-ink-900/15 px-1.5 py-1.5">
                    <span v-if="side === 'tags'" class="t-data rounded-[2px] bg-[#C0432A]/5 px-1 text-[0.68rem] text-[#C0432A]">{{ t(`home.hero.sheet.tags.${key}`) }}</span>
                    <span v-else>{{ t(`home.hero.sheet.values.${key}`) }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </figure>
      </div>
    </div>
  </section>
</template>
