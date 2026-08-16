<script setup lang="ts">
import type { DocumentTemplate, DocumentType, FieldType } from '~/types'

definePageMeta({ middleware: ['auth', 'require-tenant-admin'], layout: 'app' })

const { t } = useI18n()
const { formatDate } = useLocaleDate()
const route = useRoute()
const documentTypeId = String(route.params.id)
const { getById, update, listTemplates, uploadTemplate } = useDocumentTypes()
const { show } = useSnackbar()
const authStore = useAuthStore()
const isDemo = computed(() => authStore.user?.is_demo ?? false)

const FIELD_TYPES: FieldType[] = ['str', 'int', 'float', 'bool', 'date', 'list[str]', 'list[int]']

interface FieldRow {
  name: string
  type: FieldType
  description: string
  required: boolean
}

const loading = ref(true)
const error = ref('')
const saving = ref(false)

const name = ref('')
const description = ref('')
const promptInstructions = ref('')
const notificationEmails = ref<string[]>([])
const fieldRows = ref<FieldRow[]>([])
const isActive = ref(true)

const templates = ref<DocumentTemplate[]>([])
const templatesLoading = ref(true)
const uploadError = ref('')
const uploading = ref(false)
const fileInput = ref<File[]>([])

const templateHeaders = computed(() => [
  { title: t('admin.documentTypes.templateHeaders.file'), key: 'original_filename' },
  { title: t('admin.documentTypes.templateHeaders.version'), key: 'version' },
  { title: t('admin.common.statusLabel'), key: 'is_active' },
  { title: t('admin.documentTypes.templateHeaders.uploaded'), key: 'created_at' }
])

function applyDocumentType(doc: DocumentType) {
  name.value = doc.name
  description.value = doc.description ?? ''
  promptInstructions.value = doc.prompt_instructions ?? ''
  notificationEmails.value = [...doc.notification_emails]
  isActive.value = doc.is_active
  fieldRows.value = Object.entries(doc.field_schema).map(([fieldName, entry]) => ({
    name: fieldName,
    type: entry.type,
    description: entry.description,
    required: entry.required
  }))
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const doc = await getById(documentTypeId)
    applyDocumentType(doc)
  } catch {
    error.value = t('admin.documentTypes.errors.load')
  } finally {
    loading.value = false
  }
}

async function loadTemplates() {
  templatesLoading.value = true
  try {
    templates.value = await listTemplates(documentTypeId)
  } finally {
    templatesLoading.value = false
  }
}

function addField() {
  fieldRows.value.push({ name: '', type: 'str', description: '', required: true })
}

function removeField(index: number) {
  fieldRows.value.splice(index, 1)
}

async function onSave() {
  saving.value = true
  try {
    const fieldSchema = Object.fromEntries(
      fieldRows.value
        .filter((row) => row.name.trim())
        .map((row) => [row.name.trim(), { type: row.type, description: row.description, required: row.required }])
    )
    const updated = await update(documentTypeId, {
      name: name.value,
      description: description.value || null,
      field_schema: fieldSchema,
      prompt_instructions: promptInstructions.value || null,
      notification_emails: notificationEmails.value,
      is_active: isActive.value
    })
    applyDocumentType(updated)
    show(t('admin.documentTypes.toast.saved'), 'success')
  } catch {
    show(t('admin.documentTypes.errors.saveForm'), 'error')
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
    const message =
      (err as { data?: { detail?: string } })?.data?.detail ?? t('admin.documentTypes.errors.uploadTemplate')
    uploadError.value = message
  } finally {
    uploading.value = false
  }
}

onMounted(async () => {
  await Promise.all([load(), loadTemplates()])
})
</script>

<template>
  <div>
    <v-btn variant="text" to="/admin/document-types" class="mb-4">&larr; {{ t('admin.layout.nav.documentTypes') }}</v-btn>

    <v-alert v-if="error" type="error" variant="tonal">{{ error }}</v-alert>
    <v-skeleton-loader v-else-if="loading" type="card" />

    <template v-else>
      <v-card class="mb-6">
        <v-card-title>{{ t('admin.documentTypes.basicInfo.title') }}</v-card-title>
        <v-card-text>
          <v-text-field v-model="name" :label="t('admin.common.nameLabel')" required :disabled="isDemo" class="mb-2" />
          <v-textarea v-model="description" :label="t('admin.common.descriptionLabel')" rows="2" :disabled="isDemo" class="mb-2" />
          <v-textarea
            v-model="promptInstructions"
            :label="t('admin.documentTypes.basicInfo.promptInstructionsLabel')"
            rows="3"
            :disabled="isDemo"
            class="mb-2"
          />
          <v-combobox
            v-model="notificationEmails"
            :label="t('admin.documentTypes.basicInfo.notificationEmailsLabel')"
            multiple
            chips
            closable-chips
            :disabled="isDemo"
            :hint="t('admin.documentTypes.basicInfo.notificationEmailsHint')"
            persistent-hint
          />
          <v-switch v-model="isActive" :label="t('admin.common.status.active')" color="primary" :disabled="isDemo" class="mt-2" />
        </v-card-text>
      </v-card>

      <v-card class="mb-6">
        <v-card-title class="flex items-center justify-between">
          {{ t('admin.documentTypes.fields.title') }}
          <v-btn v-if="!isDemo" size="small" variant="text" @click="addField">{{ t('admin.documentTypes.fields.add') }}</v-btn>
        </v-card-title>
        <v-card-text>
          <div v-if="!fieldRows.length" class="py-4 text-center text-sm text-ink-900/60">
            {{ t('admin.documentTypes.fields.empty') }}
          </div>
          <div v-for="(row, index) in fieldRows" :key="index" class="mb-3 flex items-start gap-2">
            <v-text-field
              v-model="row.name"
              :label="t('admin.documentTypes.fields.nameLabel')"
              density="compact"
              hide-details
              :disabled="isDemo"
              class="flex-1"
            />
            <v-select
              v-model="row.type"
              :items="FIELD_TYPES"
              :label="t('admin.documentTypes.fields.typeLabel')"
              density="compact"
              hide-details
              :disabled="isDemo"
              class="w-40"
            />
            <v-text-field
              v-model="row.description"
              :label="t('admin.common.descriptionLabel')"
              density="compact"
              hide-details
              :disabled="isDemo"
              class="flex-1"
            />
            <v-checkbox
              v-model="row.required"
              :label="t('admin.documentTypes.fields.requiredLabel')"
              density="compact"
              hide-details
              :disabled="isDemo"
            />
            <v-btn v-if="!isDemo" icon="mdi-delete" size="small" variant="text" @click="removeField(index)" />
          </div>
        </v-card-text>
      </v-card>

      <div v-if="!isDemo" class="mb-6 flex justify-end">
        <v-btn color="primary" :loading="saving" @click="onSave">{{ t('admin.documentTypes.saveChanges') }}</v-btn>
      </div>

      <v-card>
        <v-card-title>{{ t('admin.documentTypes.templates.title') }}</v-card-title>
        <v-card-text>
          <AdminResourceTable
            :headers="templateHeaders"
            :items="templates"
            :total-items="templates.length"
            :loading="templatesLoading"
            :error="null"
          >
            <template #item.is_active="{ item }">
              <v-chip :color="item.is_active ? 'approved' : 'failed'" size="small" variant="tonal">
                {{ item.is_active ? t('admin.documentTypes.templateStatus.active') : t('admin.documentTypes.templateStatus.previous') }}
              </v-chip>
            </template>
            <template #item.created_at="{ item }">
              {{ formatDate(item.created_at) }}
            </template>
          </AdminResourceTable>

          <div v-if="!isDemo" class="mt-4 flex items-start gap-2">
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
    </template>
  </div>
</template>
