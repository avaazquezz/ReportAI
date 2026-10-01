<script setup lang="ts">
import type { ColumnType, DocumentTemplate, DocumentType, FieldSchemaEntry, FieldType } from '~/types'

definePageMeta({ middleware: ['auth', 'require-tenant-admin'], layout: 'app', titleKey: 'admin.layout.nav.documentTypes' })

const { t } = useI18n()
const { formatDate } = useLocaleDate()
const route = useRoute()
const documentTypeId = String(route.params.id)
const { getById, update, listTemplates, uploadTemplate, downloadTemplate } = useDocumentTypes()
const { show } = useSnackbar()
const authStore = useAuthStore()
const isDemo = computed(() => authStore.user?.is_demo ?? false)

const COLUMN_TYPES: ColumnType[] = ['str', 'int', 'float', 'bool', 'date', 'time', 'email', 'phone']
const FIELD_TYPES: FieldType[] = [...COLUMN_TYPES, 'list[str]', 'list[int]', 'enum', 'list[object]', 'image']
// A field is a template variable: `{{ visit_date }}` works, `{{ visit date }}` does not.
const IDENTIFIER = /^[A-Za-z_]\w*$/

interface ColumnRow {
  name: string
  type: ColumnType
  description: string
}

interface FieldRow {
  name: string
  label: string
  type: FieldType
  description: string
  required: boolean
  options: string[]
  columns: ColumnRow[]
  multiple: boolean
}

const loading = ref(true)
const error = ref('')
const saving = ref(false)
const form = ref<{ validate: () => Promise<{ valid: boolean }> } | null>(null)

const name = ref('')
const description = ref('')
const promptInstructions = ref('')
const notificationEmails = ref<string[]>([])
const fieldRows = ref<FieldRow[]>([])
const isActive = ref(true)

const templates = ref<DocumentTemplate[]>([])
const templatesLoading = ref(true)
const templatesError = ref<string | null>(null)
const uploadError = ref('')
const uploading = ref(false)
const fileInput = ref<File[]>([])

const fieldsHint = computed(() =>
  t('admin.documentTypes.fields.hint', { example: `{{ ${t('admin.documentTypes.fields.exampleName')} }}` })
)
const manualHelp = computed(() =>
  t('admin.documentTypes.templates.manualHelp', { tag: `{{ ${t('admin.documentTypes.fields.exampleName')} }}` })
)
// 'list[str]' as an i18n path would read as list → str; the keys spell it list_str.
const typeTitle = (value: FieldType) => t(`admin.documentTypes.fieldTypes.${value.replace(/\[(\w+)\]/, '_$1')}`)
const typeItems = computed(() => FIELD_TYPES.map((value) => ({ value, title: typeTitle(value) })))
const columnTypeItems = computed(() => COLUMN_TYPES.map((value) => ({ value, title: typeTitle(value) })))

const templateHeaders = computed(() => [
  { title: t('admin.documentTypes.templateHeaders.file'), key: 'original_filename' },
  { title: t('admin.documentTypes.templateHeaders.version'), key: 'version' },
  { title: t('admin.common.statusLabel'), key: 'is_active' },
  { title: t('admin.documentTypes.templateHeaders.uploaded'), key: 'created_at' },
  { title: '', key: 'actions', width: '1%' }
])

async function onDownloadTemplate(template: DocumentTemplate) {
  try {
    await downloadTemplate(documentTypeId, template)
  } catch {
    show(t('admin.documentTypes.errors.downloadTemplate'), 'error')
  }
}

const required = (value: string) => Boolean(value?.trim()) || t('admin.common.validation.required')
const identifier = (value: string) => IDENTIFIER.test(value.trim()) || t('admin.documentTypes.validation.identifier')
const emailList = (values: string[]) =>
  values.every((value) => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value)) || t('admin.common.validation.emails')

// Two fields with one name used to save as one, silently dropping the first (FE-7).
function uniqueAmong(names: () => string[]) {
  return (value: string) =>
    names().filter((other) => other.trim() === value.trim()).length < 2 || t('admin.documentTypes.validation.duplicate')
}
const uniqueField = uniqueAmong(() => fieldRows.value.map((row) => row.name))

function enumOptions(row: FieldRow) {
  return () => new Set(row.options.map((option) => option.trim()).filter(Boolean)).size >= 2 || t('admin.documentTypes.validation.options')
}

function toRow(fieldName: string, entry: FieldSchemaEntry): FieldRow {
  return {
    name: fieldName,
    label: entry.label ?? '',
    type: entry.type,
    description: entry.description ?? '',
    required: entry.required ?? true,
    options: [...(entry.options ?? [])],
    columns: Object.entries(entry.columns ?? {}).map(([columnName, column]) => ({
      name: columnName,
      type: column.type,
      description: column.description ?? ''
    })),
    multiple: entry.multiple ?? false
  }
}

function toEntry(row: FieldRow): FieldSchemaEntry {
  const entry: FieldSchemaEntry = { type: row.type, description: row.description, required: row.type === 'image' ? false : row.required }
  if (row.label.trim()) entry.label = row.label.trim()
  if (row.type === 'enum') entry.options = [...new Set(row.options.map((option) => option.trim()).filter(Boolean))]
  if (row.type === 'list[object]') {
    entry.columns = Object.fromEntries(
      row.columns.map((column) => [column.name.trim(), { type: column.type, description: column.description }])
    )
  }
  if (row.type === 'image') entry.multiple = row.multiple
  return entry
}

function applyDocumentType(doc: DocumentType) {
  name.value = doc.name
  description.value = doc.description ?? ''
  promptInstructions.value = doc.prompt_instructions ?? ''
  notificationEmails.value = [...doc.notification_emails]
  isActive.value = doc.is_active
  fieldRows.value = Object.entries(doc.field_schema).map(([fieldName, entry]) => toRow(fieldName, entry))
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    applyDocumentType(await getById(documentTypeId))
  } catch {
    error.value = t('admin.documentTypes.errors.load')
  } finally {
    loading.value = false
  }
}

async function loadTemplates() {
  templatesLoading.value = true
  templatesError.value = null
  try {
    templates.value = await listTemplates(documentTypeId)
  } catch {
    // Without this the table said "no results" when it simply failed to load (FE-6).
    templatesError.value = t('admin.documentTypes.errors.templates')
  } finally {
    templatesLoading.value = false
  }
}

function addField() {
  fieldRows.value.push(toRow('', { type: 'str', description: '', required: true }))
}

function moveField(index: number, step: -1 | 1) {
  const rows = fieldRows.value
  const target = index + step
  if (target < 0 || target >= rows.length) return
  ;[rows[index], rows[target]] = [rows[target]!, rows[index]!]
}

function addColumn(row: FieldRow) {
  row.columns.push({ name: '', type: 'str', description: '' })
}

async function onSave() {
  if (!(await form.value?.validate())?.valid) {
    show(t('admin.documentTypes.errors.invalidForm'), 'error')
    return
  }
  saving.value = true
  try {
    const updated = await update(documentTypeId, {
      name: name.value.trim(),
      description: description.value || null,
      field_schema: Object.fromEntries(fieldRows.value.map((row) => [row.name.trim(), toEntry(row)])),
      prompt_instructions: promptInstructions.value || null,
      notification_emails: notificationEmails.value,
      is_active: isActive.value
    })
    applyDocumentType(updated)
    show(t('admin.documentTypes.toast.saved'), 'success')
  } catch (err) {
    const detail = (err as { data?: { detail?: unknown } })?.data?.detail
    show(typeof detail === 'string' ? detail : t('admin.documentTypes.errors.saveForm'), 'error')
  } finally {
    saving.value = false
  }
}

async function onUpload() {
  const file = fileInput.value[0]
  if (!file) return
  uploading.value = true
  uploadError.value = ''
  try {
    await uploadTemplate(documentTypeId, file)
    fileInput.value = []
    show(t('admin.documentTypes.toast.templateUploaded'), 'success')
    await loadTemplates()
  } catch (err: unknown) {
    const detail = (err as { data?: { detail?: unknown } })?.data?.detail
    uploadError.value = typeof detail === 'string' ? detail : t('admin.documentTypes.errors.uploadTemplate')
  } finally {
    uploading.value = false
  }
}

// The assistant adds its fields to this type and activates the new template.
async function onAssistantApplied(doc: DocumentType) {
  applyDocumentType(doc)
  await loadTemplates()
}

onMounted(() => Promise.all([load(), loadTemplates()]))
</script>

<template>
  <div>
    <v-btn variant="text" to="/admin/document-types" class="mb-4" prepend-icon="mdi-arrow-left">
      {{ t('admin.layout.nav.documentTypes') }}
    </v-btn>

    <v-alert v-if="error" type="error" variant="tonal">{{ error }}</v-alert>
    <v-skeleton-loader v-else-if="loading" type="card" />

    <v-form v-else ref="form" :disabled="isDemo" @submit.prevent="onSave">
      <v-card class="mb-6">
        <v-card-title>{{ t('admin.documentTypes.basicInfo.title') }}</v-card-title>
        <v-card-text>
          <v-text-field v-model="name" :label="t('admin.common.nameLabel')" :rules="[required]" class="mb-2" />
          <v-textarea v-model="description" :label="t('admin.common.descriptionLabel')" rows="2" class="mb-2" />
          <v-textarea
            v-model="promptInstructions"
            :label="t('admin.documentTypes.basicInfo.promptInstructionsLabel')"
            rows="3"
            class="mb-2"
          />
          <v-combobox
            v-model="notificationEmails"
            :label="t('admin.documentTypes.basicInfo.notificationEmailsLabel')"
            :rules="[emailList]"
            multiple
            chips
            closable-chips
            :hint="t('admin.documentTypes.basicInfo.notificationEmailsHint')"
            persistent-hint
          />
          <v-switch v-model="isActive" :label="t('admin.common.status.active')" color="primary" class="mt-2" />
        </v-card-text>
      </v-card>

      <v-card class="mb-6">
        <v-card-title class="flex items-center justify-between">
          {{ t('admin.documentTypes.fields.title') }}
          <v-btn v-if="!isDemo" size="small" variant="text" prepend-icon="mdi-plus" @click="addField">
            {{ t('admin.documentTypes.fields.add') }}
          </v-btn>
        </v-card-title>
        <v-card-subtitle class="whitespace-normal">{{ fieldsHint }}</v-card-subtitle>
        <v-card-text>
          <div v-if="!fieldRows.length" class="py-4 text-center text-sm text-ink-900/70">
            {{ t('admin.documentTypes.fields.empty') }}
          </div>
          <div
            v-for="(row, index) in fieldRows"
            :key="index"
            class="mb-4 rounded-lg border border-slate-300 p-3"
          >
            <div class="grid grid-cols-1 gap-2 md:grid-cols-12">
              <v-text-field
                v-model="row.name"
                :label="t('admin.documentTypes.fields.nameLabel')"
                :hint="t('admin.documentTypes.fields.nameHint')"
                :rules="[required, identifier, uniqueField]"
                density="compact"
                class="md:col-span-3"
              />
              <v-text-field
                v-model="row.label"
                :label="t('admin.documentTypes.fields.labelLabel')"
                density="compact"
                class="md:col-span-3"
              />
              <v-select
                v-model="row.type"
                :items="typeItems"
                :label="t('admin.documentTypes.fields.typeLabel')"
                density="compact"
                class="md:col-span-3"
              />
              <div class="flex items-start md:col-span-3">
                <v-checkbox
                  v-if="row.type !== 'image'"
                  v-model="row.required"
                  :label="t('admin.documentTypes.fields.requiredLabel')"
                  density="compact"
                  hide-details
                />
                <v-checkbox
                  v-else
                  v-model="row.multiple"
                  :label="t('admin.documentTypes.fields.multipleLabel')"
                  density="compact"
                  hide-details
                />
                <v-spacer />
                <template v-if="!isDemo">
                  <v-btn icon="mdi-arrow-up" size="small" variant="text" :disabled="index === 0" :aria-label="t('admin.documentTypes.fields.moveUp')" @click="moveField(index, -1)" />
                  <v-btn icon="mdi-arrow-down" size="small" variant="text" :disabled="index === fieldRows.length - 1" :aria-label="t('admin.documentTypes.fields.moveDown')" @click="moveField(index, 1)" />
                  <v-btn icon="mdi-delete-outline" size="small" variant="text" :aria-label="t('admin.documentTypes.fields.remove')" @click="fieldRows.splice(index, 1)" />
                </template>
              </div>
            </div>
            <v-text-field
              v-model="row.description"
              :label="t('admin.documentTypes.fields.descriptionLabel')"
              :hint="t('admin.documentTypes.fields.descriptionHint')"
              density="compact"
            />

            <v-combobox
              v-if="row.type === 'enum'"
              v-model="row.options"
              :label="t('admin.documentTypes.fields.optionsLabel')"
              :rules="[enumOptions(row)]"
              multiple
              chips
              closable-chips
              density="compact"
            />

            <div v-if="row.type === 'list[object]'" class="mt-2 rounded bg-paper-50 p-2">
              <p class="mb-2 font-body text-sm font-medium">{{ t('admin.documentTypes.fields.columnsLabel') }}</p>
              <div v-for="(column, columnIndex) in row.columns" :key="columnIndex" class="grid grid-cols-1 gap-2 md:grid-cols-12">
                <v-text-field
                  v-model="column.name"
                  :label="t('admin.documentTypes.fields.nameLabel')"
                  :rules="[required, identifier, uniqueAmong(() => row.columns.map((c) => c.name))]"
                  density="compact"
                  class="md:col-span-3"
                />
                <v-select v-model="column.type" :items="columnTypeItems" :label="t('admin.documentTypes.fields.typeLabel')" density="compact" class="md:col-span-3" />
                <v-text-field v-model="column.description" :label="t('admin.documentTypes.fields.columnTitle')" density="compact" class="md:col-span-5" />
                <v-btn
                  v-if="!isDemo"
                  icon="mdi-close"
                  size="small"
                  variant="text"
                  class="md:col-span-1"
                  :aria-label="t('admin.documentTypes.fields.removeColumn')"
                  @click="row.columns.splice(columnIndex, 1)"
                />
              </div>
              <p v-if="!row.columns.length" class="mb-2 text-sm text-failed-600">{{ t('admin.documentTypes.validation.columns') }}</p>
              <v-btn v-if="!isDemo" size="small" variant="text" prepend-icon="mdi-plus" @click="addColumn(row)">
                {{ t('admin.documentTypes.fields.addColumn') }}
              </v-btn>
            </div>
          </div>
        </v-card-text>
      </v-card>

      <div v-if="!isDemo" class="mb-6 flex justify-end">
        <v-btn type="submit" color="primary" :loading="saving">{{ t('admin.documentTypes.saveChanges') }}</v-btn>
      </div>
    </v-form>

    <v-card v-if="!loading && !error">
      <v-card-title>{{ t('admin.documentTypes.templates.title') }}</v-card-title>
      <v-card-text>
        <template v-if="!isDemo">
          <h3 class="mb-2 font-display text-lg font-bold">{{ t('admin.assistant.title') }}</h3>
          <AdminTemplateAssistant
            :document-type-id="documentTypeId"
            :existing-fields="Object.fromEntries(fieldRows.map((row) => [row.name, row.label || row.name]))"
            @applied="onAssistantApplied"
          />
          <v-divider class="my-6" />
        </template>
        <AdminResourceTable
          :headers="templateHeaders"
          :items="templates"
          :total-items="templates.length"
          :loading="templatesLoading"
          :error="templatesError"
        >
          <template #item.is_active="{ item }">
            <v-chip :color="item.is_active ? 'approved' : 'default'" size="small" variant="tonal">
              {{ item.is_active ? t('admin.documentTypes.templateStatus.active') : t('admin.documentTypes.templateStatus.previous') }}
            </v-chip>
          </template>
          <template #item.created_at="{ item }">
            {{ formatDate(item.created_at) }}
          </template>
          <template #item.actions="{ item }">
            <v-btn size="small" variant="text" prepend-icon="mdi-download" @click="onDownloadTemplate(item)">
              {{ t('admin.documentTypes.templates.download') }}
            </v-btn>
          </template>
        </AdminResourceTable>

        <p v-if="!isDemo" class="mt-6 text-sm text-ink-900/70">{{ manualHelp }}</p>
        <div v-if="!isDemo" class="mt-2 flex items-start gap-2">
          <v-file-input
            v-model="fileInput"
            :label="t('admin.documentTypes.templates.uploadLabel')"
            accept=".docx"
            density="compact"
            hide-details
            class="flex-1"
          />
          <v-btn color="primary" :loading="uploading" :disabled="!fileInput.length" @click="onUpload">
            {{ t('admin.documentTypes.templates.uploadButton') }}
          </v-btn>
        </div>
        <v-alert v-if="uploadError" type="error" variant="tonal" class="mt-2">{{ uploadError }}</v-alert>
      </v-card-text>
    </v-card>
  </div>
</template>
