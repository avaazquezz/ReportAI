<script setup lang="ts">
// The approval stamp: the only green on the page, and only where something has been approved.
defineProps<{ label: string }>()
</script>

<template>
  <span
    class="stamp inline-block -rotate-[7deg] rounded-[3px] border-[3px] border-[#136B4F] px-3 py-1 font-plan text-[1.05rem] font-extrabold uppercase tracking-[0.14em] text-[#136B4F] [font-stretch:112.5%]"
    aria-hidden="true"
  >{{ label }}</span>
</template>
