<script setup lang="ts">
defineProps<{
  modelValue: boolean
  title: string
  message: string
  confirmText?: string
  confirmColor?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  confirm: []
}>()

function close() {
  emit('update:modelValue', false)
}

function confirm() {
  emit('confirm')
  close()
}
</script>

<template>
  <v-dialog
    :model-value="modelValue"
    max-width="420"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-card>
      <v-card-title>{{ title }}</v-card-title>
      <v-card-text>{{ message }}</v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="close">Cancelar</v-btn>
        <v-btn :color="confirmColor ?? 'error'" variant="flat" @click="confirm">
          {{ confirmText ?? 'Confirmar' }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
