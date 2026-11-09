<script setup lang="ts">
// The brand mark and wordmark, as on the favicon: an orange R on ink.
defineProps<{ dark?: boolean }>()
</script>

<template>
  <span class="inline-flex items-center gap-2.5">
    <svg viewBox="0 0 100 100" class="h-7 w-7 shrink-0" aria-hidden="true">
      <rect width="100" height="100" rx="20" class="fill-ink-900" :class="{ 'fill-white': dark }" />
      <text
        x="50"
        y="70"
        font-size="60"
        text-anchor="middle"
        font-family="Arial, Helvetica, sans-serif"
        font-weight="700"
        :class="dark ? 'fill-ink-900' : 'fill-capture-500'"
      >R</text>
    </svg>
    <span class="font-plan text-[1.15rem] font-extrabold tracking-[-0.03em]">ReportAI</span>
  </span>
</template>
