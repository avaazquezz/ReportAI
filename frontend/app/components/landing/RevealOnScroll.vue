<script setup lang="ts">
const el = ref<HTMLElement | null>(null)
const visible = useInView(el, 0.2)
</script>

<template>
  <div ref="el">
    <Transition
      appear
      enter-active-class="transition duration-700 ease-out"
      enter-from-class="opacity-0 translate-y-4"
      enter-to-class="opacity-100 translate-y-0"
    >
      <div v-if="visible">
        <slot />
      </div>
    </Transition>
  </div>
</template>
