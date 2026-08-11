<script setup lang="ts" generic="T extends Record<string, unknown>">
interface TableHeader {
  title: string
  key: string
  sortable?: boolean
  width?: string
}

defineProps<{
  headers: TableHeader[]
  items: T[]
  totalItems: number
  loading?: boolean
  error?: string | null
}>()

const emit = defineEmits<{
  'update:options': [options: { page: number; itemsPerPage: number }]
}>()

// Forward every slot the caller passes through to the underlying table (custom
// columns, row actions, …) except `no-data`, which this component owns so every
// list view gets a real empty state without repeating it at every call site.
const slots = useSlots()
const forwardedSlotNames = computed(() => Object.keys(slots).filter((name) => name !== 'no-data'))

const page = ref(1)
const itemsPerPage = ref(10)

function onUpdateOptions(options: { page: number; itemsPerPage: number }) {
  page.value = options.page
  itemsPerPage.value = options.itemsPerPage
  emit('update:options', { page: options.page, itemsPerPage: options.itemsPerPage })
}
</script>

<template>
  <div>
    <v-alert v-if="error" type="error" variant="tonal" class="mb-4">{{ error }}</v-alert>
    <v-data-table-server
      v-model:page="page"
      v-model:items-per-page="itemsPerPage"
      :headers="headers"
      :items="items"
      :items-length="totalItems"
      :loading="loading"
      :items-per-page-options="[10, 25, 50]"
      @update:options="onUpdateOptions"
    >
      <template v-for="slotName in forwardedSlotNames" :key="slotName" #[slotName]="scope">
        <slot :name="slotName" v-bind="scope ?? {}" />
      </template>
      <template #no-data>
        <div class="py-10 text-center text-ink-900/60">Sin resultados todavía.</div>
      </template>
    </v-data-table-server>
  </div>
</template>
