<script setup lang="ts" generic="T extends Record<string, unknown>">
interface TableHeader {
  title: string
  key: string
  sortable?: boolean
  width?: string
}

const props = defineProps<{
  headers: TableHeader[]
  items: T[]
  totalItems: number
  loading?: boolean
  error?: string | null
}>()

const emit = defineEmits<{
  'update:options': [options: { page: number; itemsPerPage: number }]
}>()

const { t } = useI18n()

// Forward every slot the caller passes through to the underlying table (custom
// columns, row actions, …) except `no-data`, which this component owns so every
// list view gets a real empty state without repeating it at every call site.
const slots = useSlots()
const forwardedSlotNames = computed(() => Object.keys(slots).filter((name) => name !== 'no-data'))

// Owned by the caller when it needs to jump back to page 1 (after a create, or a new filter);
// otherwise the table kept showing the old page number for the first page's rows (FE-4).
const page = defineModel<number>('page', { default: 1 })
const itemsPerPage = ref(10)

// The API pages but does not sort: a sort arrow that reorders only the visible page is a lie (FE-8).
const unsortedHeaders = computed(() => props.headers.map((header) => ({ ...header, sortable: false })))

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
      :headers="unsortedHeaders"
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
        <div class="py-10 text-center text-ink-900/60">{{ t('admin.common.noResults') }}</div>
      </template>
    </v-data-table-server>
  </div>
</template>
