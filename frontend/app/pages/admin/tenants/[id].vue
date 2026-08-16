<script setup lang="ts">
import type { Tenant } from '~/types'

definePageMeta({ middleware: ['auth', 'require-super-admin'], layout: 'app' })

const { t } = useI18n()
const { formatDate } = useLocaleDate()
const route = useRoute()
const tenantId = String(route.params.id)
const { getById, resendInvite, setActive } = useTenants()
const { show } = useSnackbar()

const tenant = ref<Tenant | null>(null)
const loading = ref(true)
const error = ref('')
const sendingInvite = ref(false)

async function load() {
  loading.value = true
  error.value = ''
  try {
    tenant.value = await getById(tenantId)
  } catch {
    error.value = t('admin.tenants.errors.load')
  } finally {
    loading.value = false
  }
}

async function onResendInvite() {
  sendingInvite.value = true
  try {
    const result = await resendInvite(tenantId)
    show(result.message, 'success')
  } catch {
    show(t('admin.tenants.errors.resendInvite'), 'error')
  } finally {
    sendingInvite.value = false
  }
}

async function onToggleActive() {
  if (!tenant.value) return
  await setActive(tenant.value.id, !tenant.value.is_active)
  show(t('admin.common.toastStatusUpdated'), 'success')
  await load()
}

onMounted(load)
</script>

<template>
  <div>
    <v-btn variant="text" to="/admin/tenants" class="mb-4">&larr; {{ t('admin.layout.nav.tenants') }}</v-btn>

    <v-alert v-if="error" type="error" variant="tonal">{{ error }}</v-alert>
    <v-skeleton-loader v-else-if="loading" type="card" />

    <v-card v-else-if="tenant">
      <v-card-title class="flex items-center justify-between">
        {{ tenant.name }}
        <v-chip :color="tenant.is_active ? 'approved' : 'failed'" size="small" variant="tonal">
          {{ tenant.is_active ? t('admin.tenants.status.active') : t('admin.tenants.status.inactive') }}
        </v-chip>
      </v-card-title>
      <v-card-text>
        <p class="font-body text-sm text-ink-900/70">{{ t('admin.tenants.detail.slug', { slug: tenant.slug }) }}</p>
        <p class="font-body text-sm text-ink-900/70">
          {{ t('admin.tenants.detail.created', { date: formatDate(tenant.created_at) }) }}
        </p>
      </v-card-text>
      <v-card-actions>
        <v-btn variant="text" :loading="sendingInvite" @click="onResendInvite">{{ t('admin.tenants.detail.resendInvite') }}</v-btn>
        <v-btn variant="text" @click="onToggleActive">
          {{ tenant.is_active ? t('admin.common.deactivate') : t('admin.common.reactivate') }}
        </v-btn>
      </v-card-actions>
    </v-card>

    <div v-if="tenant" class="mt-6">
      <h2 class="mb-4 font-display text-lg font-bold text-ink-900">{{ t('admin.layout.nav.usage') }}</h2>
      <AdminUsageSummary :tenant-id="tenant.id" />
    </div>
  </div>
</template>
