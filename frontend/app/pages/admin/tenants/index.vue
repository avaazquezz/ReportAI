<script setup lang="ts">
import type { Tenant } from '~/types'

definePageMeta({ middleware: ['auth', 'require-super-admin'], layout: 'app' })

const { t } = useI18n()
const { formatDate } = useLocaleDate()
const { items, total, loading, error, fetchList, create, setActive } = useTenants()
const { show } = useSnackbar()

const headers = computed(() => [
  { title: t('admin.common.nameLabel'), key: 'name' },
  { title: t('admin.tenants.headers.slug'), key: 'slug' },
  { title: t('admin.common.statusLabel'), key: 'is_active' },
  { title: t('admin.common.createdLabel'), key: 'created_at' },
  { title: '', key: 'actions', sortable: false, width: '1%' }
])

const createDialog = ref(false)
const creating = ref(false)
const createError = ref('')
const form = ref({ name: '', slug: '', admin_email: '', admin_full_name: '' })

const confirmDialog = ref(false)
const pendingTenant = ref<Tenant | null>(null)

async function onCreate() {
  creating.value = true
  createError.value = ''
  try {
    const result = await create(form.value)
    createDialog.value = false
    form.value = { name: '', slug: '', admin_email: '', admin_full_name: '' }
    show(
      result.invite_email_sent
        ? t('admin.tenants.toast.created')
        : t('admin.tenants.toast.createdInviteFailed'),
      result.invite_email_sent ? 'success' : 'error'
    )
    await fetchList({ page: 1, itemsPerPage: 10 })
  } catch {
    createError.value = t('admin.tenants.errors.create')
  } finally {
    creating.value = false
  }
}

function askToggle(tenant: Tenant) {
  pendingTenant.value = tenant
  confirmDialog.value = true
}

async function confirmToggle() {
  if (!pendingTenant.value) return
  await setActive(pendingTenant.value.id, !pendingTenant.value.is_active)
  show(t('admin.common.toastStatusUpdated'), 'success')
  await fetchList({ page: 1, itemsPerPage: 10 })
}
</script>

<template>
  <div>
    <div class="mb-6 flex items-center justify-between">
      <h1 class="font-display text-2xl font-bold text-ink-900">{{ t('admin.layout.nav.tenants') }}</h1>
      <v-btn color="primary" @click="createDialog = true">{{ t('admin.tenants.new') }}</v-btn>
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
          {{ item.is_active ? t('admin.tenants.status.active') : t('admin.tenants.status.inactive') }}
        </v-chip>
      </template>
      <template #item.created_at="{ item }">
        {{ formatDate(item.created_at, { year: 'numeric', month: 'short', day: 'numeric' }) }}
      </template>
      <template #item.actions="{ item }">
        <v-btn size="small" variant="text" :to="`/admin/tenants/${item.id}`">{{ t('admin.common.view') }}</v-btn>
        <v-btn size="small" variant="text" @click="askToggle(item)">
          {{ item.is_active ? t('admin.common.deactivate') : t('admin.common.reactivate') }}
        </v-btn>
      </template>
    </AdminResourceTable>

    <v-dialog v-model="createDialog" max-width="480">
      <v-card>
        <v-card-title>{{ t('admin.tenants.new') }}</v-card-title>
        <v-card-text>
          <v-form @submit.prevent="onCreate">
            <v-text-field v-model="form.name" :label="t('admin.common.nameLabel')" required class="mb-2" />
            <v-text-field
              v-model="form.slug"
              :label="t('admin.tenants.headers.slug')"
              :hint="t('admin.tenants.dialog.slugHint')"
              persistent-hint
              required
              class="mb-2"
            />
            <v-text-field v-model="form.admin_full_name" :label="t('admin.tenants.dialog.adminNameLabel')" required class="mb-2" />
            <v-text-field v-model="form.admin_email" :label="t('admin.tenants.dialog.adminEmailLabel')" type="email" required class="mb-2" />
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

    <AdminConfirmDialog
      v-model="confirmDialog"
      :title="t('admin.common.changeStatus')"
      :message="
        pendingTenant?.is_active
          ? t('admin.common.confirmToggle.deactivate', { name: pendingTenant?.name })
          : t('admin.common.confirmToggle.reactivate', { name: pendingTenant?.name })
      "
      confirm-color="primary"
      @confirm="confirmToggle"
    />
  </div>
</template>
