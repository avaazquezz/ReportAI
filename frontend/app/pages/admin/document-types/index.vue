<script setup lang="ts">
import type { DocumentType, StarterTemplate } from '~/types'

definePageMeta({ middleware: ['auth', 'require-tenant-admin'], layout: 'app', titleKey: 'admin.layout.nav.documentTypes' })

const { t } = useI18n()
const { items, total, loading, error, fetchList, create } = useDocumentTypes()
const { show } = useSnackbar()
const router = useRouter()
const authStore = useAuthStore()
const isDemo = computed(() => authStore.user?.is_demo ?? false)

const headers = computed(() => [
  { title: t('admin.common.nameLabel'), key: 'name' },
  { title: t('admin.common.descriptionLabel'), key: 'description' },
  { title: t('admin.common.statusLabel'), key: 'is_active' },
  { title: '', key: 'actions', sortable: false, width: '1%' }
])

const createDialog = ref(false)
const creating = ref(false)
const createError = ref('')
const form = ref({ name: '', description: '' })
const formRef = ref<{ validate: () => Promise<{ valid: boolean }> } | null>(null)
const required = (value: string) => Boolean(value?.trim()) || t('admin.common.validation.required')

async function onCreate() {
  if (!(await formRef.value?.validate())?.valid) return
  creating.value = true
  createError.value = ''
  try {
    const result = await create({
      name: form.value.name,
      description: form.value.description || null,
      field_schema: {},
      prompt_instructions: null,
      notification_emails: []
    })
    createDialog.value = false
    form.value = { name: '', description: '' }
    show(t('admin.documentTypes.toast.created'), 'success')
    await router.push(`/admin/document-types/${result.id}`)
  } catch {
    createError.value = t('admin.documentTypes.errors.create')
  } finally {
    creating.value = false
  }
}

// Ready-made types for a company with no template of its own yet.
const startersDialog = ref(false)
const starters = ref<StarterTemplate[]>([])
const installing = ref<string | null>(null)

async function openStarters() {
  startersDialog.value = true
  if (starters.value.length) return
  try {
    starters.value = await useApi()<StarterTemplate[]>('/starter-templates')
  } catch {
    show(t('admin.starters.errors.load'), 'error')
  }
}

async function install(key: string) {
  installing.value = key
  try {
    const created = await useApi()<DocumentType>(`/starter-templates/${key}/install`, { method: 'POST' })
    show(t('admin.starters.installed', { name: created.name }), 'success')
    await router.push(`/admin/document-types/${created.id}`)
  } catch {
    show(t('admin.starters.errors.install'), 'error')
  } finally {
    installing.value = null
  }
}
</script>

<template>
  <div>
    <div class="mb-2 flex items-center justify-between">
      <h1 class="font-display text-2xl font-bold text-ink-900">{{ t('admin.layout.nav.documentTypes') }}</h1>
      <div v-if="!isDemo" class="flex gap-2">
        <v-btn variant="tonal" prepend-icon="mdi-file-star-outline" @click="openStarters">{{ t('admin.starters.open') }}</v-btn>
        <v-btn color="primary" @click="createDialog = true">{{ t('admin.documentTypes.new') }}</v-btn>
      </div>
    </div>
    <p class="mb-6 text-ink-900/70">{{ t('admin.documentTypes.help') }}</p>

    <AdminResourceTable
      :headers="headers"
      :items="items"
      :total-items="total"
      :loading="loading"
      :error="error"
      @update:options="fetchList"
    >
      <template #item.is_active="{ item }">
        <v-chip :color="item.is_active ? 'approved' : 'failed'" size="small" variant="tonal">
          {{ item.is_active ? t('admin.common.status.active') : t('admin.common.status.inactive') }}
        </v-chip>
      </template>
      <template #item.actions="{ item }">
        <v-btn size="small" variant="text" :to="`/admin/document-types/${item.id}`">
          {{ isDemo ? t('admin.common.view') : t('admin.common.edit') }}
        </v-btn>
      </template>
    </AdminResourceTable>

    <v-dialog v-model="startersDialog" max-width="720">
      <v-card>
        <v-card-title>{{ t('admin.starters.title') }}</v-card-title>
        <v-card-text>
          <p class="mb-4 text-ink-900/80">{{ t('admin.starters.help') }}</p>
          <v-progress-linear v-if="!starters.length" indeterminate color="primary" />
          <div class="grid gap-4 md:grid-cols-3">
            <v-card v-for="starter in starters" :key="starter.key" rounded="lg" elevation="0" border class="flex flex-col pa-4">
              <h3 class="font-display font-bold">{{ starter.name }}</h3>
              <p class="mt-1 flex-1 text-sm text-ink-900/80">{{ starter.description }}</p>
              <p class="mt-3 text-xs text-ink-900/70">{{ starter.fields.join(' · ') }}</p>
              <v-btn class="mt-4" color="primary" variant="tonal" :loading="installing === starter.key" @click="install(starter.key)">
                {{ t('admin.starters.use') }}
              </v-btn>
            </v-card>
          </div>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="startersDialog = false">{{ t('admin.common.close') }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="createDialog" max-width="480">
      <v-card>
        <v-card-title>{{ t('admin.documentTypes.dialog.newTitle') }}</v-card-title>
        <v-card-text>
          <v-form ref="formRef" @submit.prevent="onCreate">
            <v-text-field v-model="form.name" :label="t('admin.common.nameLabel')" :rules="[required]" class="mb-2" />
            <v-textarea v-model="form.description" :label="t('admin.common.descriptionLabel')" rows="2" class="mb-2" />
            <v-alert v-if="createError" type="error" variant="tonal" class="mb-2">{{ createError }}</v-alert>
            <div class="mt-2 flex justify-end gap-2">
              <v-btn variant="text" @click="createDialog = false">{{ t('admin.common.cancel') }}</v-btn>
              <v-btn type="submit" color="primary" :loading="creating">{{ t('admin.common.create') }}</v-btn>
            </div>
          </v-form>
        </v-card-text>
      </v-card>
    </v-dialog>
  </div>
</template>
