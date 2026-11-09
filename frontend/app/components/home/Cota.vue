<script setup lang="ts">
// A dimension line from a technical drawing: end ticks, a rule, the measure in the middle. The
// page's quiet signature, over the sheets it measures.
defineProps<{ label: string }>()
</script>

<template>
  <div class="cota flex items-center gap-3 text-ink-900/60" aria-hidden="true">
    <span class="h-3 w-px bg-current" />
    <span class="cota-rule h-px flex-1 origin-left bg-current" />
    <span class="t-data shrink-0 text-ink-900/60">{{ label }}</span>
    <span class="cota-rule h-px flex-1 origin-right bg-current" />
    <span class="h-3 w-px bg-current" />
  </div>
</template>
