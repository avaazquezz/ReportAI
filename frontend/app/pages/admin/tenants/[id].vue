<script setup lang="ts">
import type { PlanKey, PlanStatus, Tenant } from '~/types'

definePageMeta({ middleware: ['auth', 'require-super-admin'], layout: 'app', titleKey: 'admin.layout.nav.tenants' })

const { t } = useI18n()
const { formatDate } = useLocaleDate()
const route = useRoute()
const tenantId = String(route.params.id)
const { getById, resendInvite, setActive, setPlan } = useTenants()
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
  try {
    await setActive(tenant.value.id, !tenant.value.is_active)
    show(t('admin.common.toastStatusUpdated'), 'success')
    await load()
  } catch {
    show(t('admin.common.errors.statusUpdate'), 'error')
  }
}

const PLANS: PlanKey[] = ['unlimited', 'trial', 'starter', 'pro', 'business']
const STATUSES: PlanStatus[] = ['trialing', 'active', 'past_due', 'canceled']
const planItems = computed(() => PLANS.map((value) => ({ value, title: t(`admin.plan.names.${value}`) })))
const statusItems = computed(() => STATUSES.map((value) => ({ value, title: t(`admin.plan.status.${value}`) })))
const savingPlan = ref(false)

async function onPlanChange(change: { plan?: PlanKey; plan_status?: PlanStatus }) {
  if (!tenant.value) return
  savingPlan.value = true
  try {
    tenant.value = await setPlan(tenant.value.id, change)
    show(t('admin.plan.toastSaved'), 'success')
  } catch {
    show(t('admin.plan.errors.save'), 'error')
  } finally {
    savingPlan.value = false
  }
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
        <div class="mt-4 grid max-w-xl grid-cols-1 gap-4 sm:grid-cols-2">
          <v-select
            :model-value="tenant.plan"
            :items="planItems"
            :label="t('admin.plan.planLabel')"
            :loading="savingPlan"
            :disabled="savingPlan"
            :hint="t('admin.plan.planHint')"
            persistent-hint
            @update:model-value="(plan: PlanKey) => onPlanChange({ plan })"
          />
          <v-select
            :model-value="tenant.plan_status"
            :items="statusItems"
            :label="t('admin.plan.statusLabel')"
            :disabled="savingPlan"
            @update:model-value="(plan_status: PlanStatus) => onPlanChange({ plan_status })"
          />
        </div>
        <p v-if="tenant.plan_period_end" class="mt-2 font-body text-sm text-ink-900/70">
          {{ t('admin.plan.periodEnd', { date: formatDate(tenant.plan_period_end) }) }}
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
