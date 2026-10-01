<script setup lang="ts">
import type { ColumnType, FieldSchemaEntry, FieldValue } from '~/types'

const props = defineProps<{
  schema: Record<string, FieldSchemaEntry>
  evidence?: Record<string, string> | null
  readonly?: boolean
}>()
const values = defineModel<Record<string, FieldValue>>({ required: true })

const { t } = useI18n()

// Numbers, dates and yes/no need little room; text columns take the rest of the table.
const NARROW_COLUMNS: ColumnType[] = ['int', 'float', 'bool', 'date', 'time']

const INPUT_TYPES: Partial<Record<ColumnType, string>> = {
  int: 'number',
  float: 'number',
  date: 'date',
  time: 'time',
  email: 'email',
  phone: 'tel'
}

// Photos are not typed in: they arrive with the report and show next to it.
const fields = computed(() =>
  Object.entries(props.schema).filter(([, spec]) => spec.type !== 'image')
)

const boolItems = computed(() => [
  { title: t('admin.reportFields.yes'), value: true },
  { title: t('admin.reportFields.no'), value: false }
])

function label(name: string, spec: { label?: string | null }) {
  return spec.label || name.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase())
}

function isEmpty(value: unknown) {
  return value === null || value === undefined || (typeof value === 'string' && !value.trim())
}

function isMissing(name: string, spec: FieldSchemaEntry) {
  return spec.required && isEmpty(values.value[name])
}

// An emptied input means "nobody said it" (null), not an empty string in the document.
function scalar(type: ColumnType, raw: unknown): string | number | null {
  if (raw === null || raw === undefined || raw === '') return null
  if (type === 'int') return Number.parseInt(String(raw), 10)
  if (type === 'float') return Number.parseFloat(String(raw))
  return String(raw)
}

function setField(name: string, value: FieldValue) {
  values.value = { ...values.value, [name]: value }
}

function setList(name: string, type: string, raw: unknown[]) {
  const items = raw.map((item) => String(item).trim()).filter(Boolean)
  setField(name, type === 'list[int]' ? items.map(Number).filter(Number.isFinite) : items)
}

function rows(name: string): Array<Record<string, unknown>> {
  const value = values.value[name]
  return Array.isArray(value) ? (value as Array<Record<string, unknown>>) : []
}

function setCell(name: string, index: number, column: string, type: ColumnType, raw: unknown) {
  const next = rows(name).map((row, i) => (i === index ? { ...row, [column]: type === 'bool' ? raw : scalar(type, raw) } : row))
  setField(name, next as FieldValue)
}

function addRow(name: string) {
  setField(name, [...rows(name), {}] as FieldValue)
}

function removeRow(name: string, index: number) {
  setField(name, rows(name).filter((_, i) => i !== index) as FieldValue)
}
</script>

<template>
  <div>
    <div v-for="[name, spec] in fields" :key="name" class="mb-5">
      <template v-if="spec.type === 'list[object]'">
        <p class="mb-2 font-body text-sm font-medium text-ink-900">
          {{ label(name, spec) }}<span v-if="spec.required" aria-hidden="true"> *</span>
        </p>
        <div class="overflow-x-auto">
          <table class="w-full border-collapse font-body text-sm">
            <thead>
              <tr>
                <th
                  v-for="(column, key) in spec.columns ?? {}"
                  :key="key"
                  class="border-b border-slate-300 px-2 py-1 text-left font-medium"
                  :class="{ 'w-36': NARROW_COLUMNS.includes(column.type) }"
                >
                  {{ column.description || key }}
                </th>
                <th class="w-0" />
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, index) in rows(name)" :key="index">
                <td v-for="(column, key) in spec.columns ?? {}" :key="key" class="px-1 py-1">
                  <v-checkbox
                    v-if="column.type === 'bool'"
                    :model-value="Boolean(row[key])"
                    :readonly="readonly"
                    :aria-label="column.description || String(key)"
                    density="compact"
                    hide-details
                    @update:model-value="setCell(name, index, String(key), column.type, $event)"
                  />
                  <v-text-field
                    v-else
                    :model-value="row[key] ?? ''"
                    :type="INPUT_TYPES[column.type] ?? 'text'"
                    :readonly="readonly"
                    :aria-label="column.description || String(key)"
                    density="compact"
                    variant="outlined"
                    hide-details
                    @update:model-value="setCell(name, index, String(key), column.type, $event)"
                  />
                </td>
                <td>
                  <v-btn
                    v-if="!readonly"
                    icon="mdi-close"
                    size="small"
                    variant="text"
                    :aria-label="t('admin.reportFields.removeRow')"
                    @click="removeRow(name, index)"
                  />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-if="!rows(name).length" class="py-2 text-sm text-ink-900/70">{{ t('admin.reportFields.emptyTable') }}</p>
        <v-btn v-if="!readonly" size="small" variant="text" prepend-icon="mdi-plus" @click="addRow(name)">
          {{ t('admin.reportFields.addRow') }}
        </v-btn>
      </template>

      <v-select
        v-else-if="spec.type === 'bool'"
        :model-value="values[name] ?? null"
        :items="boolItems"
        :label="label(name, spec)"
        :readonly="readonly"
        :error-messages="isMissing(name, spec) ? t('admin.reportFields.requiredMissing') : []"
        clearable
        density="comfortable"
        hide-details="auto"
        @update:model-value="setField(name, $event ?? null)"
      />

      <v-select
        v-else-if="spec.type === 'enum'"
        :model-value="typeof values[name] === 'string' ? values[name] : null"
        :items="spec.options ?? []"
        :label="label(name, spec)"
        :readonly="readonly"
        :error-messages="isMissing(name, spec) ? t('admin.reportFields.requiredMissing') : []"
        clearable
        density="comfortable"
        hide-details="auto"
        @update:model-value="setField(name, $event ?? null)"
      />

      <v-combobox
        v-else-if="spec.type === 'list[str]' || spec.type === 'list[int]'"
        :model-value="Array.isArray(values[name]) ? values[name] : []"
        :label="label(name, spec)"
        :readonly="readonly"
        multiple
        chips
        closable-chips
        density="comfortable"
        hide-details="auto"
        @update:model-value="setList(name, spec.type, $event)"
      />

      <v-textarea
        v-else-if="spec.type === 'str'"
        :model-value="values[name] ?? ''"
        :label="label(name, spec)"
        :readonly="readonly"
        :error-messages="isMissing(name, spec) ? t('admin.reportFields.requiredMissing') : []"
        rows="1"
        auto-grow
        density="comfortable"
        hide-details="auto"
        @update:model-value="setField(name, scalar('str', $event))"
      />

      <v-text-field
        v-else
        :model-value="values[name] ?? ''"
        :type="INPUT_TYPES[spec.type as ColumnType] ?? 'text'"
        :label="label(name, spec)"
        :readonly="readonly"
        :error-messages="isMissing(name, spec) ? t('admin.reportFields.requiredMissing') : []"
        density="comfortable"
        hide-details="auto"
        @update:model-value="setField(name, scalar(spec.type as ColumnType, $event))"
      />

      <p v-if="evidence?.[name]" class="mt-1 font-body text-xs text-ink-900/70">
        <v-icon icon="mdi-format-quote-open" size="x-small" aria-hidden="true" />
        {{ t('admin.reportFields.evidence', { quote: evidence[name] }) }}
      </p>
    </div>
  </div>
</template>
