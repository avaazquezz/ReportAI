<script setup lang="ts">
// Sheet 7, the revision table: the decisions that shape the system, dated (the day the decision or
// its first commit landed), each with the serious alternative that was turned down and what that
// would have cost. Then what the system doesn't do yet. A real table on wide screens; one card per
// decision on a phone.
const { t } = useI18n()

const ROWS = ['graph', 'queue', 'empty', 'onecode', 'rls', 'pwa', 'login', 'sw', 'lock'] as const
const COLUMNS = ['why', 'rejected'] as const
const LIMITS = ['billing', 'cycle', 'languages', 'ios', 'rls'] as const
const row = (key: string, field: string) => t(`landing.revisions.rows.${key}.${field}`)
</script>

<template>
  <section :id="SHEET_IDS.revisions" class="scroll-mt-20 bg-surface-0" data-tone="light">
    <div class="mx-auto max-w-[1240px] px-6 py-20 lg:py-28">
      <LandingSheetHead sheet="revisions" :heading="t('landing.revisions.heading')" :plain="t('landing.revisions.plain')" />

      <table class="mt-14 hidden w-full border-collapse border-2 border-ink-900 text-left md:table">
        <thead>
          <tr class="border-b-2 border-ink-900 font-body text-[13px] text-ink-900">
            <th scope="col" class="w-[7.5rem] px-4 py-3 font-semibold">{{ t('landing.revisions.columns.date') }}</th>
            <th scope="col" class="w-[24%] px-4 py-3 font-semibold">{{ t('landing.revisions.columns.decision') }}</th>
            <th v-for="col in COLUMNS" :key="col" scope="col" class="px-4 py-3 font-semibold">{{ t(`landing.revisions.columns.${col}`) }}</th>
          </tr>
        </thead>
        <tbody class="font-body text-[14px] leading-snug text-ink-900/85">
          <tr v-for="key in ROWS" :key="key" class="border-b border-ink-900/15 align-top last:border-b-0">
            <td class="whitespace-nowrap px-4 py-3.5 font-mono text-[12px] tabular-nums text-ink-900/70">{{ row(key, 'date') }}</td>
            <th scope="row" class="px-4 py-3.5 font-plan text-[14.5px] font-bold leading-snug text-ink-900">{{ row(key, 'decision') }}</th>
            <td class="px-4 py-3.5">{{ row(key, 'why') }}</td>
            <td class="px-4 py-3.5 text-ink-900/70">{{ row(key, 'rejected') }}</td>
          </tr>
        </tbody>
      </table>

      <ol class="m-0 mt-12 list-none p-0 md:hidden">
        <li v-for="key in ROWS" :key="key" class="border-t-2 border-ink-900 py-5">
          <p class="m-0 font-mono text-[12px] tabular-nums text-ink-900/60">{{ row(key, 'date') }}</p>
          <p class="mb-0 mt-1 font-plan text-[1.05rem] font-bold leading-snug text-ink-900">{{ row(key, 'decision') }}</p>
          <dl class="m-0 mt-3 space-y-2.5 font-body text-[14px] leading-snug">
            <div v-for="col in COLUMNS" :key="col">
              <dt class="font-semibold text-ink-900">{{ t(`landing.revisions.columns.${col}`) }}</dt>
              <dd class="m-0 mt-0.5 text-ink-900/80">{{ row(key, col) }}</dd>
            </div>
          </dl>
        </li>
      </ol>

      <div class="mt-16 grid gap-6 lg:grid-cols-12">
        <h3 class="m-0 font-plan text-[1.35rem] font-extrabold tracking-[-0.02em] text-ink-900 lg:col-span-4">{{ t('landing.revisions.limitsTitle') }}</h3>
        <ul class="m-0 list-none p-0 lg:col-span-8">
          <li v-for="limit in LIMITS" :key="limit" class="border-b border-ink-900/15 py-3 font-body text-[15px] leading-snug text-ink-900/85 first:border-t">
            {{ t(`landing.revisions.limits.${limit}`) }}
          </li>
        </ul>
      </div>
    </div>
  </section>
</template>
