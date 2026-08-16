<script setup lang="ts">
definePageMeta({ middleware: ['auth', 'require-tenant-admin'], layout: 'app' })

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

async function onCreate() {
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
</script>

<template>
  <div>
    <div class="mb-6 flex items-center justify-between">
      <h1 class="font-display text-2xl font-bold text-ink-900">{{ t('admin.layout.nav.documentTypes') }}</h1>
      <v-btn v-if="!isDemo" color="primary" @click="createDialog = true">{{ t('admin.documentTypes.new') }}</v-btn>
    </div>

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

    <v-dialog v-model="createDialog" max-width="480">
      <v-card>
        <v-card-title>{{ t('admin.documentTypes.dialog.newTitle') }}</v-card-title>
        <v-card-text>
          <v-form @submit.prevent="onCreate">
            <v-text-field v-model="form.name" :label="t('admin.common.nameLabel')" required class="mb-2" />
            <v-textarea v-model="form.description" :label="t('admin.common.descriptionLabel')" rows="2" class="mb-2" />
            <v-alert v-if="createError" type="error" variant="tonal" class="mb-2">{{ createError }}</v-alert>
          </v-form>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="createDialog = false">{{ t('admin.common.cancel') }}</v-btn>
          <v-btn color="primary" :loading="creating" @click="onCreate">{{ t('admin.common.create') }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>
