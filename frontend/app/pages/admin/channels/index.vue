<script setup lang="ts">
import type { ChannelConnection, ChannelType } from '~/types'

definePageMeta({ middleware: ['auth', 'require-tenant-admin'], layout: 'app' })

const { t } = useI18n()
const { items, total, loading, error, fetchList, create, update } = useChannelConnections()
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

async function onSave() {
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
    await fetchList({ page: 1, itemsPerPage: 10 })
  } catch {
    saveError.value = t('admin.channels.errors.save')
  } finally {
    saving.value = false
  }
}

const confirmDialog = ref(false)
const pendingConnection = ref<ChannelConnection | null>(null)

function askToggle(connection: ChannelConnection) {
  pendingConnection.value = connection
  confirmDialog.value = true
}

async function confirmToggle() {
  if (!pendingConnection.value) return
  await update(pendingConnection.value.id, {
    display_name: pendingConnection.value.display_name,
    allowed_senders: pendingConnection.value.allowed_senders,
    is_active: !pendingConnection.value.is_active
  })
  show(t('admin.common.toastStatusUpdated'), 'success')
  await fetchList({ page: 1, itemsPerPage: 10 })
}
</script>

<template>
  <div>
    <div class="mb-6 flex items-center justify-between">
      <h1 class="font-display text-2xl font-bold text-ink-900">{{ t('admin.layout.nav.channels') }}</h1>
      <v-btn v-if="!isDemo" color="primary" @click="openCreate">{{ t('admin.channels.new') }}</v-btn>
    </div>

    <AdminResourceTable
      :headers="headers"
      :items="items"
      :total-items="total"
      :loading="loading"
      :error="error"
      @update:options="fetchList"
    >
      <template #item.channel_type="{ item }">
        {{ CHANNEL_TYPES.find((c) => c.value === item.channel_type)?.title ?? item.channel_type }}
      </template>
      <template #item.allowed_senders="{ item }">
        <span v-if="!item.allowed_senders.length" class="text-ink-900/60">{{ t('admin.channels.allSenders') }}</span>
        <span v-else>{{ item.allowed_senders.length }}</span>
      </template>
      <template #item.is_active="{ item }">
        <v-chip :color="item.is_active ? 'approved' : 'failed'" size="small" variant="tonal">
          {{ item.is_active ? t('admin.common.status.active') : t('admin.common.status.inactive') }}
        </v-chip>
      </template>
      <template #item.actions="{ item }">
        <template v-if="!isDemo">
          <v-btn size="small" variant="text" @click="openEdit(item)">{{ t('admin.common.edit') }}</v-btn>
          <v-btn size="small" variant="text" @click="askToggle(item)">
            {{ item.is_active ? t('admin.common.deactivate') : t('admin.common.reactivate') }}
          </v-btn>
        </template>
      </template>
    </AdminResourceTable>

    <v-dialog v-model="dialog" max-width="520">
      <v-card>
        <v-card-title>{{ editingId ? t('admin.channels.dialog.editTitle') : t('admin.channels.new') }}</v-card-title>
        <v-card-text>
          <v-form @submit.prevent="onSave">
            <v-select
              v-model="channelType"
              :items="CHANNEL_TYPES"
              item-title="title"
              item-value="value"
              :label="t('admin.channels.dialog.channelTypeLabel')"
              :disabled="!!editingId"
              class="mb-2"
            />
            <v-text-field v-model="displayName" :label="t('admin.common.nameLabel')" required class="mb-2" />

            <template v-if="channelType === 'telegram'">
              <v-text-field
                v-model="botToken"
                :label="t('admin.channels.dialog.botTokenLabel')"
                :placeholder="editingId ? t('admin.channels.dialog.leaveBlank') : ''"
                class="mb-2"
              />
            </template>
            <template v-else-if="channelType === 'whatsapp'">
              <v-text-field
                v-model="phoneNumberId"
                :label="t('admin.channels.dialog.phoneNumberIdLabel')"
                :placeholder="editingId ? t('admin.channels.dialog.leaveBlank') : ''"
                class="mb-2"
              />
              <v-text-field
                v-model="accessToken"
                :label="t('admin.channels.dialog.accessTokenLabel')"
                :placeholder="editingId ? t('admin.channels.dialog.leaveBlank') : ''"
                class="mb-2"
              />
            </template>
            <template v-else>
              <v-text-field
                v-model="inboundSlug"
                :label="t('admin.channels.dialog.inboundSlugLabel')"
                :placeholder="editingId ? t('admin.channels.dialog.leaveBlank') : ''"
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
          </v-form>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="dialog = false">{{ t('admin.common.cancel') }}</v-btn>
          <v-btn color="primary" :loading="saving" @click="onSave">{{ t('admin.common.save') }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

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
