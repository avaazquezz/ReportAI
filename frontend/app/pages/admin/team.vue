<script setup lang="ts">
import type { TeamInviteResult, TeamMember, TenantRole } from '~/types'

definePageMeta({ middleware: ['auth', 'require-tenant-admin'], layout: 'app', titleKey: 'admin.layout.nav.team' })

const { t } = useI18n()
const api = useApi()
const { show } = useSnackbar()
const authStore = useAuthStore()
const { formatDate } = useLocaleDate()

const ROLES = computed<{ value: TenantRole; title: string; subtitle: string }[]>(() =>
  (['tenant_admin', 'approver', 'viewer'] as const).map((value) => ({
    value,
    title: t(`admin.roles.${value}`),
    subtitle: t(`admin.team.roleHelp.${value}`)
  }))
)

const members = ref<TeamMember[]>([])
const loading = ref(false)
const loadError = ref('')

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    members.value = await api<TeamMember[]>('/team')
  } catch {
    loadError.value = t('admin.team.errors.load')
  } finally {
    loading.value = false
  }
}
onMounted(load)

const headers = computed(() => [
  { title: t('admin.common.nameLabel'), key: 'full_name' },
  { title: 'Email', key: 'email' },
  { title: t('admin.team.role'), key: 'role' },
  { title: t('admin.common.statusLabel'), key: 'is_active' },
  { title: '', key: 'actions', sortable: false, width: '1%' }
])

function errorText(err: unknown, fallback: string) {
  const detail = (err as { data?: { detail?: unknown } })?.data?.detail
  return typeof detail === 'string' ? detail : fallback
}

// ── Inviting ───────────────────────────────────────────────────────────────────────────
const inviteDialog = ref(false)
const invite = reactive({ full_name: '', email: '', role: 'approver' as TenantRole })
const inviteForm = ref<{ validate: () => Promise<{ valid: boolean }> } | null>(null)
const inviting = ref(false)
const inviteError = ref('')
const linkToShare = ref<{ name: string; link: string } | null>(null)
const required = (v: string) => Boolean(v?.trim()) || t('admin.common.validation.required')
const email = (v: string) => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v ?? '') || t('admin.common.validation.email')

function openInvite() {
  Object.assign(invite, { full_name: '', email: '', role: 'approver' })
  inviteError.value = ''
  inviteDialog.value = true
}

function handOut(result: TeamInviteResult) {
  if (result.invite_email_sent) show(t('admin.team.toast.invited', { email: result.member.email }), 'success')
  else if (result.invite_link) linkToShare.value = { name: result.member.full_name, link: result.invite_link }
}

async function sendInvite() {
  if (!(await inviteForm.value?.validate())?.valid) return
  inviting.value = true
  inviteError.value = ''
  try {
    handOut(await api<TeamInviteResult>('/team', { method: 'POST', body: invite }))
    inviteDialog.value = false
    await load()
  } catch (err) {
    inviteError.value = errorText(err, t('admin.team.errors.invite'))
  } finally {
    inviting.value = false
  }
}

async function resendInvite(member: TeamMember) {
  try {
    handOut(await api<TeamInviteResult>(`/team/${member.id}/invite`, { method: 'POST' }))
  } catch (err) {
    show(errorText(err, t('admin.team.errors.invite')), 'error')
  }
}

async function copy(text: string) {
  await navigator.clipboard.writeText(text)
  show(t('admin.common.copied'), 'success')
}

// ── Changing someone's access ──────────────────────────────────────────────────────────
async function changeRole(member: TeamMember, role: TenantRole) {
  try {
    await api(`/team/${member.id}`, { method: 'PATCH', body: { role } })
    show(t('admin.team.toast.roleChanged', { name: member.full_name }), 'success')
  } catch (err) {
    show(errorText(err, t('admin.team.errors.update')), 'error')
  }
  await load()
}

const confirmDialog = ref(false)
const pending = ref<TeamMember | null>(null)

async function confirmToggle() {
  if (!pending.value) return
  try {
    await api(`/team/${pending.value.id}`, { method: 'PATCH', body: { is_active: !pending.value.is_active } })
    show(t('admin.common.toastStatusUpdated'), 'success')
    await load()
  } catch (err) {
    show(errorText(err, t('admin.team.errors.update')), 'error')
  }
}
</script>

<template>
  <div>
    <div class="mb-2 flex items-center justify-between">
      <h1 class="font-display text-2xl font-bold text-ink-900">{{ t('admin.layout.nav.team') }}</h1>
      <v-btn color="primary" prepend-icon="mdi-account-plus-outline" @click="openInvite">{{ t('admin.team.invite') }}</v-btn>
    </div>
    <p class="mb-6 text-ink-900/70">{{ t('admin.team.help') }}</p>

    <v-alert v-if="loadError" type="error" variant="tonal" class="mb-4">{{ loadError }}</v-alert>
    <v-card rounded="lg" elevation="0" border>
      <v-data-table :headers="headers" :items="members" :loading="loading" :items-per-page="-1" hide-default-footer>
        <template #item.full_name="{ item }">
          {{ item.full_name }}
          <v-chip v-if="item.id === authStore.user?.id" size="x-small" class="ml-1" label>{{ t('admin.team.you') }}</v-chip>
        </template>
        <template #item.role="{ item }">
          <v-select
            :model-value="item.role"
            :items="ROLES"
            :disabled="item.id === authStore.user?.id"
            :aria-label="t('admin.team.role')"
            density="compact"
            variant="plain"
            hide-details
            class="max-w-[180px]"
            @update:model-value="(role: TenantRole) => changeRole(item, role)"
          />
        </template>
        <template #item.is_active="{ item }">
          <v-chip :color="item.is_active ? 'approved' : 'failed'" size="small" variant="tonal">
            {{ item.is_active ? t('admin.common.status.active') : t('admin.common.status.inactive') }}
          </v-chip>
        </template>
        <template #item.actions="{ item }">
          <div v-if="item.id !== authStore.user?.id" class="flex justify-end whitespace-nowrap">
            <v-btn v-if="item.is_active" size="small" variant="text" @click="resendInvite(item)">{{ t('admin.team.resend') }}</v-btn>
            <v-btn size="small" variant="text" @click="pending = item; confirmDialog = true">
              {{ item.is_active ? t('admin.common.deactivate') : t('admin.common.reactivate') }}
            </v-btn>
          </div>
        </template>
      </v-data-table>
    </v-card>

    <v-dialog v-model="inviteDialog" max-width="520">
      <v-card>
        <v-card-title>{{ t('admin.team.invite') }}</v-card-title>
        <v-card-text>
          <v-form ref="inviteForm" @submit.prevent="sendInvite">
            <v-text-field v-model="invite.full_name" :label="t('admin.common.nameLabel')" :rules="[required]" />
            <v-text-field v-model="invite.email" label="Email" type="email" :rules="[required, email]" />
            <v-select v-model="invite.role" :items="ROLES" :label="t('admin.team.role')" item-props />
            <p class="text-sm text-ink-900/70">{{ t('admin.team.inviteHelp') }}</p>
            <v-alert v-if="inviteError" type="error" variant="tonal" class="mt-3">{{ inviteError }}</v-alert>
            <div class="mt-4 flex justify-end gap-2">
              <v-btn variant="text" @click="inviteDialog = false">{{ t('admin.common.cancel') }}</v-btn>
              <v-btn type="submit" color="primary" :loading="inviting">{{ t('admin.team.send') }}</v-btn>
            </div>
          </v-form>
        </v-card-text>
      </v-card>
    </v-dialog>

    <v-dialog :model-value="!!linkToShare" max-width="560" @update:model-value="linkToShare = null">
      <v-card v-if="linkToShare">
        <v-card-title>{{ t('admin.team.linkTitle', { name: linkToShare.name }) }}</v-card-title>
        <v-card-text>
          <p class="mb-3">{{ t('admin.team.linkHelp') }}</p>
          <v-text-field :model-value="linkToShare.link" readonly hide-details density="compact">
            <template #append-inner>
              <v-btn icon="mdi-content-copy" size="small" variant="text" :aria-label="t('admin.common.copy')" @click="copy(linkToShare.link)" />
            </template>
          </v-text-field>
          <p class="mt-3 text-sm text-ink-900/70">{{ t('admin.team.linkExpires', { date: formatDate(new Date(Date.now() + 7 * 864e5)) }) }}</p>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn color="primary" @click="linkToShare = null">{{ t('admin.common.close') }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <AdminConfirmDialog
      v-model="confirmDialog"
      :title="t('admin.common.changeStatus')"
      :message="
        pending?.is_active
          ? t('admin.team.confirmDeactivate', { name: pending?.full_name })
          : t('admin.common.confirmToggle.reactivate', { name: pending?.full_name })
      "
      confirm-color="primary"
      @confirm="confirmToggle"
    />
  </div>
</template>
