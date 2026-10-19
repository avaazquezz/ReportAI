<script setup lang="ts">
// The product's own gesture: a {{ tag }} in the client's Word that becomes its value. The tag
// shows until a section timeline swaps it (.tok-tag out, .tok-val in); app.vue's <noscript>
// style shows the resolved value for visitors without JS.
const props = defineProps<{ tag: string; value: string }>()

// Vue's template tokenizer reads a literal "{{" inside a mustache as a nested interpolation,
// so the braces are added here.
const label = computed(() => `{{ ${props.tag} }}`)
</script>

<template>
  <span class="inline-grid align-top">
    <span class="tok-tag col-start-1 row-start-1 font-mono text-[0.92em] text-capture-600" aria-hidden="true">{{ label }}</span>
    <span class="tok-val col-start-1 row-start-1 opacity-0">{{ value }}</span>
  </span>
</template>
