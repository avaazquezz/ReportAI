<script setup lang="ts">
import type { DocumentType, FieldType, ProposedField, TemplateDraft, TemplateProposal } from '~/types'

// existingFields: the document type's own fields (name → label), to offer removing the ones the
// new template no longer prints.
const props = defineProps<{ documentTypeId: string; existingFields: Record<string, string> }>()
const emit = defineEmits<{ applied: [DocumentType] }>()

const { t } = useI18n()
const api = useApi()
const { show } = useSnackbar()

const SCALAR_TYPES: FieldType[] = ['str', 'int', 'float', 'bool', 'date', 'time', 'email', 'phone', 'enum']
const typeTitle = (value: FieldType) => t(`admin.documentTypes.fieldTypes.${value.replace(/\[(\w+)\]/, '_$1')}`)
const base = computed(() => `/document-types/${props.documentTypeId}/template-assistant`)

const file = ref<File | null>(null)
const analyzing = ref(false)
const error = ref('')
const draft = ref<TemplateDraft | null>(null)
const proposal = ref<TemplateProposal | null>(null)

function errorText(err: unknown, fallback: string) {
  const detail = (err as { data?: { detail?: unknown } })?.data?.detail
  return typeof detail === 'string' ? detail : fallback
}

async function analyze() {
  if (!file.value) return
  analyzing.value = true
  error.value = ''
  try {
    const body = new FormData()
    body.append('file', file.value)
    const result = await api<TemplateDraft>(base.value, { method: 'POST', body })
    // Cloned from the plain response: a reactive proxy can't be structuredClone'd.
    proposal.value = structuredClone(result.proposal)
    draft.value = result
  } catch (err) {
    error.value = errorText(err, t('admin.assistant.errors.analyze'))
  } finally {
    analyzing.value = false
  }
}

function reset() {
  draft.value = null
  proposal.value = null
  keep.value = []
  file.value = null
  error.value = ''
}

// ── The map: each value in its context, and where tables and lists go ────────────────────
function context(blockId: string, text: string): [string, string, string] {
  const whole = draft.value?.blocks[blockId] ?? ''
  const at = whole.indexOf(text)
  if (at < 0) return [whole, '', '']
  const before = whole.slice(Math.max(0, at - 40), at)
  return [(at > 40 ? '…' : '') + before, text, whole.slice(at + text.length, at + text.length + 40)]
}

function fieldsOfKind(kind: 'value' | 'table' | 'list') {
  return (proposal.value?.fields ?? [])
    .filter((f) => (kind === 'table' ? f.type === 'list[object]' : kind === 'list' ? f.type.startsWith('list[') && f.type !== 'list[object]' : SCALAR_TYPES.includes(f.type)))
    .map((f) => ({ value: f.name, title: f.label || f.name }))
}

function tableCaption(tableId: string, first: number, last: number) {
  const rows = draft.value?.tables[tableId] ?? []
  const header = rows[0]?.join(' · ') ?? ''
  return t('admin.assistant.tableRows', { header, first: first + 1, last: last + 1 })
}

// A field nothing points at any more goes with its last value: it would be asked for and never printed.
function dropMapping(kind: 'values' | 'tables' | 'lists', index: number) {
  const p = proposal.value!
  p[kind].splice(index, 1)
  const used = new Set([...p.values, ...p.tables, ...p.lists].map((m) => m.field))
  p.fields = p.fields.filter((f) => used.has(f.name))
}

function removeField(field: ProposedField) {
  const p = proposal.value!
  p.fields = p.fields.filter((f) => f !== field)
  p.values = p.values.filter((v) => v.field !== field.name)
  p.tables = p.tables.filter((v) => v.field !== field.name)
  p.lists = p.lists.filter((v) => v.field !== field.name)
}

function rename(field: ProposedField, name: string) {
  const p = proposal.value!
  for (const mapping of [...p.values, ...p.tables, ...p.lists]) if (mapping.field === field.name) mapping.field = name
  field.name = name
}

const IDENTIFIER = /^[a-z][a-z0-9_]{0,59}$/
const nameRule = (value: string) => IDENTIFIER.test(value) || t('admin.assistant.validation.name')
const duplicates = computed(() => {
  const names = (proposal.value?.fields ?? []).map((f) => f.name)
  return new Set(names.filter((n, i) => names.indexOf(n) !== i))
})
const invalid = computed(
  () =>
    !proposal.value ||
    duplicates.value.size > 0 ||
    proposal.value.fields.some((f) => !IDENTIFIER.test(f.name) || (f.type === 'enum' && new Set(f.options ?? []).size < 2))
)

// ── Fields of the document type the new template won't print ──────────────────────────
const unused = computed(() => {
  const names = new Set(proposal.value?.fields.map((f) => f.name) ?? [])
  return Object.keys(props.existingFields).filter((name) => !names.has(name))
})
const keep = ref<string[]>([]) // the ones the admin chose to keep anyway

// ── Preview and apply ──────────────────────────────────────────────────────────────────
const previewUrl = ref<string | null>(null)
const previewOpen = ref(false)
const previewing = ref<'labels' | 'example' | null>(null)
const applying = ref(false)

async function preview(mode: 'labels' | 'example') {
  if (!draft.value || !proposal.value) return
  previewing.value = mode
  try {
    const blob = await api<Blob>(`${base.value}/${draft.value.id}/preview`, {
      method: 'POST',
      body: { proposal: proposal.value, mode },
      responseType: 'blob'
    })
    if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = URL.createObjectURL(blob)
    previewOpen.value = true
  } catch (err) {
    // A blob response's error body is a Blob too: read it for the API's explanation.
    const data = (err as { data?: unknown })?.data
    const text = data instanceof Blob ? await data.text() : ''
    let detail = ''
    try {
      detail = JSON.parse(text).detail
    } catch {
      detail = ''
    }
    show(typeof detail === 'string' && detail ? detail : t('admin.assistant.errors.preview'), 'error')
  } finally {
    previewing.value = null
  }
}

// The PDF is dropped once the dialog has finished closing: dropping it at once collapsed the
// dialog mid-animation, and its overlay swallowed the next click.
function forgetPreview() {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = null
}

async function apply() {
  if (!draft.value || !proposal.value) return
  applying.value = true
  try {
    const body = { ...proposal.value, remove_fields: unused.value.filter((name) => !keep.value.includes(name)) }
    const updated = await api<DocumentType>(`${base.value}/${draft.value.id}/apply`, { method: 'POST', body })
    show(t('admin.assistant.applied'), 'success')
    reset()
    emit('applied', updated)
  } catch (err) {
    show(errorText(err, t('admin.assistant.errors.apply')), 'error')
  } finally {
    applying.value = false
  }
}

onBeforeUnmount(forgetPreview)
</script>

<template>
  <div>
    <!-- Upload -->
    <template v-if="!draft">
      <p class="mb-3 text-ink-900/80">{{ t('admin.assistant.intro') }}</p>
      <div class="flex items-start gap-2">
        <v-file-input
          v-model="file"
          accept=".docx"
          :label="t('admin.assistant.upload')"
          prepend-icon="mdi-file-word-outline"
          density="compact"
          hide-details
          class="flex-1"
        />
        <v-btn color="primary" :disabled="!file" :loading="analyzing" @click="analyze">{{ t('admin.assistant.analyze') }}</v-btn>
      </div>
      <p v-if="analyzing" class="mt-2 text-sm text-ink-900/70">{{ t('admin.assistant.analyzing') }}</p>
    </template>
    <v-alert v-if="error" type="error" variant="tonal" class="mt-3">{{ error }}</v-alert>

    <!-- Review -->
    <template v-else-if="draft && proposal">
      <div class="mb-4 flex items-center justify-between gap-4">
        <div>
          <p class="font-medium">{{ draft.filename }}</p>
          <p class="text-sm text-ink-900/70">
            {{ draft.already_tagged ? t('admin.assistant.alreadyTagged') : t('admin.assistant.review', { n: proposal.fields.length }) }}
          </p>
        </div>
        <v-btn variant="text" @click="reset">{{ t('admin.assistant.startOver') }}</v-btn>
      </div>

      <template v-if="!draft.already_tagged">
        <h4 class="mb-2 font-display font-bold">{{ t('admin.assistant.mapTitle') }}</h4>
        <p v-if="!proposal.values.length && !proposal.tables.length && !proposal.lists.length" class="text-sm text-ink-900/70">
          {{ t('admin.assistant.nothingFound') }}
        </p>
        <v-table density="compact" class="mb-6">
          <tbody>
            <tr v-for="(value, i) in proposal.values" :key="`v${i}`">
              <td class="py-2">
                <span class="text-ink-900/60">{{ context(value.block_id, value.text)[0] }}</span>
                <mark class="rounded bg-capture-100 px-1">{{ context(value.block_id, value.text)[1] }}</mark>
                <span class="text-ink-900/60">{{ context(value.block_id, value.text)[2] }}</span>
              </td>
              <td class="w-56">
                <v-select v-model="value.field" :items="fieldsOfKind('value')" density="compact" variant="plain" hide-details :aria-label="t('admin.assistant.field')" />
              </td>
              <td class="w-10">
                <v-btn icon="mdi-close" size="small" variant="text" :aria-label="t('admin.assistant.keepAsIs')" @click="dropMapping('values', i)" />
              </td>
            </tr>
            <tr v-for="(table, i) in proposal.tables" :key="`t${i}`">
              <td class="py-2">
                <v-icon icon="mdi-table" size="18" class="mr-1" />{{ tableCaption(table.table_id, table.first_row, table.last_row) }}
              </td>
              <td class="w-56">
                <v-select v-model="table.field" :items="fieldsOfKind('table')" density="compact" variant="plain" hide-details :aria-label="t('admin.assistant.field')" />
              </td>
              <td class="w-10">
                <v-btn icon="mdi-close" size="small" variant="text" :aria-label="t('admin.assistant.keepAsIs')" @click="dropMapping('tables', i)" />
              </td>
            </tr>
            <tr v-for="(list, i) in proposal.lists" :key="`l${i}`">
              <td class="py-2">
                <v-icon icon="mdi-format-list-bulleted" size="18" class="mr-1" />
                {{ t('admin.assistant.listItems', { first: draft.blocks[list.block_ids[0] ?? ''] ?? '', n: list.block_ids.length }) }}
              </td>
              <td class="w-56">
                <v-select v-model="list.field" :items="fieldsOfKind('list')" density="compact" variant="plain" hide-details :aria-label="t('admin.assistant.field')" />
              </td>
              <td class="w-10">
                <v-btn icon="mdi-close" size="small" variant="text" :aria-label="t('admin.assistant.keepAsIs')" @click="dropMapping('lists', i)" />
              </td>
            </tr>
          </tbody>
        </v-table>
      </template>

      <h4 class="mb-2 font-display font-bold">{{ t('admin.assistant.fieldsTitle') }}</h4>
      <!-- Keyed by position: keyed by name, renaming a field would rebuild its inputs mid-typing. -->
      <div v-for="(field, index) in proposal.fields" :key="index" class="mb-3 rounded border border-slate-300 p-3">
        <div class="grid gap-3 md:grid-cols-12">
          <v-text-field
            :model-value="field.label"
            class="md:col-span-4"
            :label="t('admin.assistant.label')"
            density="compact"
            hide-details="auto"
            @update:model-value="(v: string) => (field.label = v)"
          />
          <v-text-field
            :model-value="field.name"
            class="md:col-span-3"
            :label="t('admin.assistant.name')"
            :rules="[nameRule, (v: string) => !duplicates.has(v) || t('admin.documentTypes.validation.duplicate')]"
            density="compact"
            hide-details="auto"
            @update:model-value="(v: string) => rename(field, v)"
          />
          <v-select
            v-model="field.type"
            class="md:col-span-3"
            :items="(SCALAR_TYPES.includes(field.type) ? SCALAR_TYPES : [field.type]).map((v) => ({ value: v, title: typeTitle(v) }))"
            :label="t('admin.documentTypes.fields.typeLabel')"
            density="compact"
            hide-details
          />
          <div class="flex items-center justify-between md:col-span-2">
            <v-checkbox v-model="field.required" :label="t('admin.documentTypes.fields.requiredLabel')" density="compact" hide-details />
            <v-btn icon="mdi-delete-outline" size="small" variant="text" :aria-label="t('admin.documentTypes.fields.remove')" @click="removeField(field)" />
          </div>
        </div>
        <v-text-field
          v-model="field.description"
          class="mt-2"
          :label="t('admin.documentTypes.fields.descriptionLabel')"
          density="compact"
          hide-details
        />
        <v-combobox
          v-if="field.type === 'enum'"
          v-model="field.options"
          class="mt-2"
          :label="t('admin.documentTypes.fields.optionsLabel')"
          :rules="[(v: string[] | null) => new Set(v ?? []).size >= 2 || t('admin.documentTypes.validation.options')]"
          multiple
          chips
          closable-chips
          density="compact"
        />
        <p v-if="field.columns?.length" class="mt-2 text-sm text-ink-900/70">
          {{ t('admin.assistant.columns', { columns: field.columns.map((c) => c.name).join(', ') }) }}
        </p>
      </div>

      <template v-if="unused.length">
        <h4 class="mb-1 mt-6 font-display font-bold">{{ t('admin.assistant.unusedTitle') }}</h4>
        <p class="mb-2 text-sm text-ink-900/70">{{ t('admin.assistant.unusedHelp') }}</p>
        <v-checkbox
          v-for="name in unused"
          :key="name"
          :model-value="!keep.includes(name)"
          :label="t('admin.assistant.removeField', { field: existingFields[name] || name, name })"
          density="compact"
          hide-details
          @update:model-value="(remove: boolean | null) => (keep = remove ? keep.filter((n) => n !== name) : [...keep, name])"
        />
      </template>

      <div class="mt-4 flex flex-wrap justify-end gap-2">
        <v-btn variant="tonal" :disabled="invalid" :loading="previewing === 'labels'" @click="preview('labels')">{{ t('admin.assistant.previewLabels') }}</v-btn>
        <v-btn v-if="!draft.already_tagged" variant="tonal" :disabled="invalid" :loading="previewing === 'example'" @click="preview('example')">
          {{ t('admin.assistant.previewExample') }}
        </v-btn>
        <v-btn color="primary" :disabled="invalid" :loading="applying" @click="apply">{{ t('admin.assistant.apply') }}</v-btn>
      </div>
    </template>

    <v-dialog v-model="previewOpen" max-width="960" @after-leave="forgetPreview">
      <v-card>
        <v-card-title class="flex items-center justify-between">
          {{ t('admin.assistant.previewTitle') }}
          <v-btn icon="mdi-close" variant="text" :aria-label="t('admin.common.close')" @click="previewOpen = false" />
        </v-card-title>
        <iframe v-if="previewUrl" :src="previewUrl" class="h-[75vh] w-full" :title="t('admin.assistant.previewTitle')" />
      </v-card>
    </v-dialog>
  </div>
</template>
