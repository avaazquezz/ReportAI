<script setup lang="ts">
import type { DocumentTemplate, DocumentType, FieldType } from '~/types'

definePageMeta({ middleware: ['auth', 'require-tenant-admin'], layout: 'app' })

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

const templateHeaders = [
  { title: 'Archivo', key: 'original_filename' },
  { title: 'Versión', key: 'version' },
  { title: 'Estado', key: 'is_active' },
  { title: 'Subido', key: 'created_at' }
]

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
    error.value = 'No se pudo cargar el tipo de documento.'
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
    show('Cambios guardados.', 'success')
  } catch {
    show('No se pudo guardar. Revisa los datos del formulario.', 'error')
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
    show('Plantilla subida.', 'success')
    await loadTemplates()
  } catch (err: unknown) {
    const message =
      (err as { data?: { detail?: string } })?.data?.detail ?? 'No se pudo subir la plantilla.'
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
    <v-btn variant="text" to="/admin/document-types" class="mb-4">&larr; Tipos de documento</v-btn>

    <v-alert v-if="error" type="error" variant="tonal">{{ error }}</v-alert>
    <v-skeleton-loader v-else-if="loading" type="card" />

    <template v-else>
      <v-card class="mb-6">
        <v-card-title>Información básica</v-card-title>
        <v-card-text>
          <v-text-field v-model="name" label="Nombre" required :disabled="isDemo" class="mb-2" />
          <v-textarea v-model="description" label="Descripción" rows="2" :disabled="isDemo" class="mb-2" />
          <v-textarea
            v-model="promptInstructions"
            label="Instrucciones para la extracción"
            rows="3"
            :disabled="isDemo"
            class="mb-2"
          />
          <v-combobox
            v-model="notificationEmails"
            label="Destinatarios de notificación"
            multiple
            chips
            closable-chips
            :disabled="isDemo"
            hint="Emails que reciben cada informe generado con este tipo"
            persistent-hint
          />
          <v-switch v-model="isActive" label="Activo" color="primary" :disabled="isDemo" class="mt-2" />
        </v-card-text>
      </v-card>

      <v-card class="mb-6">
        <v-card-title class="flex items-center justify-between">
          Campos a extraer
          <v-btn v-if="!isDemo" size="small" variant="text" @click="addField">+ Añadir campo</v-btn>
        </v-card-title>
        <v-card-text>
          <div v-if="!fieldRows.length" class="py-4 text-center text-sm text-ink-900/60">
            Sin campos todavía. Añade al menos uno para poder generar informes.
          </div>
          <div v-for="(row, index) in fieldRows" :key="index" class="mb-3 flex items-start gap-2">
            <v-text-field
              v-model="row.name"
              label="Nombre del campo"
              density="compact"
              hide-details
              :disabled="isDemo"
              class="flex-1"
            />
            <v-select
              v-model="row.type"
              :items="FIELD_TYPES"
              label="Tipo"
              density="compact"
              hide-details
              :disabled="isDemo"
              class="w-40"
            />
            <v-text-field
              v-model="row.description"
              label="Descripción"
              density="compact"
              hide-details
              :disabled="isDemo"
              class="flex-1"
            />
            <v-checkbox
              v-model="row.required"
              label="Obligatorio"
              density="compact"
              hide-details
              :disabled="isDemo"
            />
            <v-btn v-if="!isDemo" icon="mdi-delete" size="small" variant="text" @click="removeField(index)" />
          </div>
        </v-card-text>
      </v-card>

      <div v-if="!isDemo" class="mb-6 flex justify-end">
        <v-btn color="primary" :loading="saving" @click="onSave">Guardar cambios</v-btn>
      </div>

      <v-card>
        <v-card-title>Plantillas</v-card-title>
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
                {{ item.is_active ? 'Activa' : 'Anterior' }}
              </v-chip>
            </template>
            <template #item.created_at="{ item }">
              {{ new Date(item.created_at).toLocaleDateString('es-ES') }}
            </template>
          </AdminResourceTable>

          <div v-if="!isDemo" class="mt-4 flex items-start gap-2">
            <v-file-input
              v-model="fileInput"
              label="Subir nueva plantilla (.docx)"
              accept=".docx"
              density="compact"
              hide-details
              class="flex-1"
            />
            <v-btn color="primary" :loading="uploading" :disabled="!fileInput.length" @click="onUpload">
              Subir
            </v-btn>
          </div>
          <v-alert v-if="uploadError" type="error" variant="tonal" class="mt-2">{{ uploadError }}</v-alert>
        </v-card-text>
      </v-card>
    </template>
  </div>
</template>
