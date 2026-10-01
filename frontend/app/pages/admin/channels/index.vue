<script setup lang="ts">
import type { ChannelConnection, ChannelType } from '~/types'

definePageMeta({ middleware: ['auth', 'require-tenant-admin'], layout: 'app', titleKey: 'admin.layout.nav.channels' })

const { t } = useI18n()
const { items, total, loading, error, fetchList, create, update } = useChannelConnections()
const { page, load, reload } = useTablePaging(fetchList)
const { show } = useSnackbar()
const authStore = useAuthStore()
const isDemo = computed(() => authStore.user?.is_demo ?? false)

const CHANNEL_TYPES: { value: ChannelType; title: string }[] = [
  { value: 'telegram', title: 'Telegram' },
  { value: 'whatsapp', title: 'WhatsApp' },
  { value: 'email', title: 'Email' }
]

const headers = computed(() => [
  { title: t('admin.common.nameLabel'), key: 'display_name' },
  { title: t('admin.channels.headers.channelType'), key: 'channel_type' },
  { title: t('admin.channels.headers.allowedSenders'), key: 'allowed_senders' },
  { title: t('admin.common.statusLabel'), key: 'is_active' },
  { title: '', key: 'actions', sortable: false, width: '1%' }
])

const dialog = ref(false)
const form = ref<{ validate: () => Promise<{ valid: boolean }> } | null>(null)
const editingId = ref<string | null>(null)
const saving = ref(false)
const saveError = ref('')

const displayName = ref('')
const channelType = ref<ChannelType>('telegram')
const botToken = ref('')
const phoneNumberId = ref('')
const accessToken = ref('')
const inboundSlug = ref('')
const allowedSenders = ref<string[]>([])
const isActive = ref(true)

function resetForm() {
  editingId.value = null
  displayName.value = ''
  channelType.value = 'telegram'
  botToken.value = ''
  phoneNumberId.value = ''
  accessToken.value = ''
  inboundSlug.value = ''
  allowedSenders.value = []
  isActive.value = true
  saveError.value = ''
}

function openCreate() {
  resetForm()
  dialog.value = true
}

function openEdit(connection: ChannelConnection) {
  resetForm()
  editingId.value = connection.id
  displayName.value = connection.display_name
  channelType.value = connection.channel_type
  allowedSenders.value = [...connection.allowed_senders]
  isActive.value = connection.is_active
  dialog.value = true
}

function buildCredentials(): Record<string, string> {
  if (channelType.value === 'telegram') {
    return botToken.value ? { bot_token: botToken.value } : {}
  }
  if (channelType.value === 'whatsapp') {
    const creds: Record<string, string> = {}
    if (phoneNumberId.value) creds.phone_number_id = phoneNumberId.value
    if (accessToken.value) creds.access_token = accessToken.value
    return creds
  }
  return inboundSlug.value ? { inbound_slug: inboundSlug.value } : {}
}

const required = (value: string) => Boolean(value?.trim()) || t('admin.common.validation.required')
// A new channel needs its credentials; editing one may leave them blank to keep the stored ones.
const credentialRules = computed(() => (editingId.value ? [] : [required]))

async function onSave() {
  if (!(await form.value?.validate())?.valid) return
  saving.value = true
  saveError.value = ''
  try {
    if (editingId.value) {
      await update(editingId.value, {
        display_name: displayName.value,
        credentials: buildCredentials(),
        allowed_senders: allowedSenders.value,
        is_active: isActive.value
      })
    } else {
      await create({
        channel_type: channelType.value,
        display_name: displayName.value,
        credentials: buildCredentials(),
        allowed_senders: allowedSenders.value
      })
    }
    dialog.value = false
    show(t('admin.channels.toast.saved'), 'success')
    await reload()
  } catch (err) {
    // Saving a Telegram bot registers its webhook, so the API can explain why Telegram said no
    // (e.g. a wrong token); validation errors arrive as a list and keep the generic text.
    const detail = (err as { data?: { detail?: unknown } })?.data?.detail
    saveError.value = typeof detail === 'string' ? detail : t('admin.channels.errors.save')
  } finally {
    saving.value = false
  }
}

const invitesFor = ref<ChannelConnection | null>(null)

const confirmDialog = ref(false)
const pendingConnection = ref<ChannelConnection | null>(null)

function askToggle(connection: ChannelConnection) {
  pendingConnection.value = connection
  confirmDialog.value = true
}

async function confirmToggle() {
  if (!pendingConnection.value) return
  try {
    await update(pendingConnection.value.id, {
      display_name: pendingConnection.value.display_name,
      allowed_senders: pendingConnection.value.allowed_senders,
      is_active: !pendingConnection.value.is_active
    })
    show(t('admin.common.toastStatusUpdated'), 'success')
    await reload()
  } catch {
    // An unhandled rejection here used to fail silently (FE-6).
    show(t('admin.common.errors.statusUpdate'), 'error')
  }
}
</script>

<template>
  <div>
    <div class="mb-6 flex items-center justify-between">
      <h1 class="font-display text-2xl font-bold text-ink-900">{{ t('admin.layout.nav.channels') }}</h1>
      <v-btn v-if="!isDemo" color="primary" @click="openCreate">{{ t('admin.channels.new') }}</v-btn>
    </div>

    <AdminResourceTable
      v-model:page="page"
      :headers="headers"
      :items="items"
      :total-items="total"
      :loading="loading"
      :error="error"
      @update:options="load"
    >
      <template #item.channel_type="{ item }">
        {{ CHANNEL_TYPES.find((c) => c.value === item.channel_type)?.title ?? item.channel_type }}
        <span v-if="item.bot_username" class="block text-xs text-ink-900/70">@{{ item.bot_username }}</span>
      </template>
      <template #item.allowed_senders="{ item }">
        <span v-if="!item.allowed_senders.length" class="text-ink-900/70">{{ t('admin.channels.allSenders') }}</span>
        <div v-else class="flex flex-wrap gap-1 py-1">
          <v-chip v-for="sender in item.allowed_senders.slice(0, 3)" :key="sender" size="x-small" label>
            {{ item.sender_labels[sender] ?? sender }}
          </v-chip>
          <v-chip v-if="item.allowed_senders.length > 3" size="x-small" label>+{{ item.allowed_senders.length - 3 }}</v-chip>
        </div>
      </template>
      <template #item.is_active="{ item }">
        <v-chip :color="item.is_active ? 'approved' : 'failed'" size="small" variant="tonal">
          {{ item.is_active ? t('admin.common.status.active') : t('admin.common.status.inactive') }}
        </v-chip>
      </template>
      <template #item.actions="{ item }">
        <div v-if="!isDemo" class="flex justify-end whitespace-nowrap">
          <v-btn size="small" variant="tonal" color="primary" prepend-icon="mdi-account-plus-outline" @click="invitesFor = item">
            {{ t('admin.invites.open') }}
          </v-btn>
          <v-btn size="small" variant="text" @click="openEdit(item)">{{ t('admin.common.edit') }}</v-btn>
          <v-btn size="small" variant="text" @click="askToggle(item)">
            {{ item.is_active ? t('admin.common.deactivate') : t('admin.common.reactivate') }}
          </v-btn>
        </div>
      </template>
    </AdminResourceTable>

    <v-dialog v-model="dialog" max-width="520">
      <v-card>
        <v-card-title>{{ editingId ? t('admin.channels.dialog.editTitle') : t('admin.channels.new') }}</v-card-title>
        <v-card-text>
          <v-form ref="form" @submit.prevent="onSave">
            <v-select
              v-model="channelType"
              :items="CHANNEL_TYPES"
              item-title="title"
              item-value="value"
              :label="t('admin.channels.dialog.channelTypeLabel')"
              :disabled="!!editingId"
              class="mb-2"
            />
            <v-text-field v-model="displayName" :label="t('admin.common.nameLabel')" :rules="[required]" class="mb-2" />

            <template v-if="channelType === 'telegram'">
              <v-text-field
                v-model="botToken"
                :label="t('admin.channels.dialog.botTokenLabel')"
                :placeholder="editingId ? t('admin.channels.dialog.leaveBlank') : ''"
                :rules="credentialRules"
                type="password"
                autocomplete="off"
                class="mb-2"
              />
            </template>
            <template v-else-if="channelType === 'whatsapp'">
              <v-text-field
                v-model="phoneNumberId"
                :label="t('admin.channels.dialog.phoneNumberIdLabel')"
                :placeholder="editingId ? t('admin.channels.dialog.leaveBlank') : ''"
                :rules="credentialRules"
                class="mb-2"
              />
              <v-text-field
                v-model="accessToken"
                :label="t('admin.channels.dialog.accessTokenLabel')"
                :placeholder="editingId ? t('admin.channels.dialog.leaveBlank') : ''"
                :rules="credentialRules"
                type="password"
                autocomplete="off"
                class="mb-2"
              />
            </template>
            <template v-else>
              <v-text-field
                v-model="inboundSlug"
                :label="t('admin.channels.dialog.inboundSlugLabel')"
                :placeholder="editingId ? t('admin.channels.dialog.leaveBlank') : ''"
                :rules="credentialRules"
                class="mb-2"
              />
            </template>

            <v-combobox
              v-model="allowedSenders"
              :label="t('admin.channels.headers.allowedSenders')"
              multiple
              chips
              closable-chips
              :hint="t('admin.channels.dialog.allowedSendersHint')"
              persistent-hint
              class="mb-2"
            />
            <v-switch v-if="editingId" v-model="isActive" :label="t('admin.common.status.active')" color="primary" />
            <v-alert v-if="saveError" type="error" variant="tonal" class="mt-2">{{ saveError }}</v-alert>
            <div class="mt-4 flex justify-end gap-2">
              <v-btn variant="text" @click="dialog = false">{{ t('admin.common.cancel') }}</v-btn>
              <v-btn type="submit" color="primary" :loading="saving">{{ t('admin.common.save') }}</v-btn>
            </div>
          </v-form>
        </v-card-text>
      </v-card>
    </v-dialog>

    <AdminSenderInvites
      v-if="invitesFor"
      :model-value="!!invitesFor"
      :connection="invitesFor"
      @update:model-value="(open: boolean) => !open && (invitesFor = null)"
      @changed="reload"
    />

    <AdminConfirmDialog
      v-model="confirmDialog"
      :title="t('admin.common.changeStatus')"
      :message="
        pendingConnection?.is_active
          ? t('admin.common.confirmToggle.deactivate', { name: pendingConnection?.display_name })
          : t('admin.common.confirmToggle.reactivate', { name: pendingConnection?.display_name })
      "
      confirm-color="primary"
      @confirm="confirmToggle"
    />
  </div>
</template>
