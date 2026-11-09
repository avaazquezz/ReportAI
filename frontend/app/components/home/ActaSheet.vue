<script lang="ts">
export interface ActaRow {
  key: string
  /** The field's name in the template, shown as {{ tag }} until the value arrives. */
  tag?: string
  label: string
  value: string | null
  missing?: boolean
}
</script>

<script setup lang="ts">
// A page of the client's own visit report, drawn in code: the company's mark, the document title
// and one ruled line per field. In `tagged` mode each field shows its template tag ({{ obra }})
// until a timeline swaps in the value (LandingToken); otherwise it shows the value, or a "missing"
// note in the reviewer's red. The company is the visitor's own ("Tu empresa", a "LOGO" mark), never
// a made-up firm that could be mistaken for a real one.
defineProps<{
  company: string
  mark: string
  title: string
  rows: ActaRow[]
  tagged?: boolean
  emptyLabel?: string
  missingLabel?: string
}>()
</script>

<template>
  <article class="sheet relative rounded-[2px] px-[clamp(1.25rem,0.6rem+2.6vw,2.75rem)] pb-12 pt-8">
    <header class="flex items-center gap-4 border-b border-ink-900/10 pb-6">
      <span class="grid h-11 w-11 shrink-0 place-items-center rounded-[3px] bg-doc-700 text-[0.8rem] font-semibold tracking-wide text-white" aria-hidden="true">
        {{ mark }}
      </span>
      <div class="min-w-0">
        <p class="m-0 text-[0.78rem] text-ink-900/60">{{ company }}</p>
        <p class="m-0 text-[1.05rem] font-semibold uppercase tracking-[0.02em] text-doc-700">{{ title }}</p>
      </div>
    </header>

    <dl class="m-0 mt-5 grid gap-y-3.5 md:gap-y-2.5">
      <div v-for="row in rows" :key="row.key" class="acta-row grid gap-1 md:grid-cols-[9.5rem_minmax(0,1fr)] md:items-end md:gap-3" :data-field="row.key">
        <dt class="text-[0.75rem] font-semibold text-ink-900/60 md:pb-[0.45rem]">{{ row.label }}</dt>
        <dd class="field-rule m-0 min-h-[1.9rem] pb-1.5 pt-1 text-[0.95rem] leading-snug" :class="{ 'is-filled': !tagged && !!row.value }">
          <LandingToken v-if="tagged && row.value" :tag="row.tag ?? row.key" :value="row.value" />
          <span v-else-if="row.value">
            <!-- A list or a table: one item or row per line, apart enough to tell where one ends. -->
            <span v-for="(line, i) in row.value.split('\n')" :key="i" class="block" :class="{ 'mt-1.5': i > 0 }">{{ line }}</span>
          </span>
          <span v-else-if="row.missing" class="text-[0.85rem] font-semibold text-[#C0432A]">{{ missingLabel }}</span>
          <span v-else class="t-data text-ink-900/60">{{ emptyLabel }}</span>
        </dd>
      </div>
    </dl>
    <slot />
  </article>
</template>
