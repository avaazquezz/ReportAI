<script setup lang="ts">
import type { ChannelConnection, SenderInvite, SenderInviteCreated } from '~/types'

const props = defineProps<{ connection: ChannelConnection }>()
const emit = defineEmits<{ changed: [] }>()
const open = defineModel<boolean>({ required: true })

const { t } = useI18n()
const api = useApi()
const { show } = useSnackbar()
const { formatDateTime } = useLocaleDate()

const invites = ref<SenderInvite[]>([])
const label = ref('')
const creating = ref(false)
const created = ref<SenderInviteCreated | null>(null)
const error = ref('')
const base = computed(() => `/channels/${props.connection.id}/invites`)

async function load() {
  try {
    invites.value = await api<SenderInvite[]>(base.value)
  } catch {
    error.value = t('admin.invites.errors.load')
  }
}

watch(open, (isOpen) => {
  if (!isOpen) return
  label.value = ''
  created.value = null
  error.value = ''
  load()
}, { immediate: true })

async function create() {
  if (!label.value.trim()) return
  creating.value = true
  error.value = ''
  try {
    created.value = await api<SenderInviteCreated>(base.value, { method: 'POST', body: { label: label.value.trim() } })
    label.value = ''
    await load()
  } catch (err) {
    const detail = (err as { data?: { detail?: unknown } })?.data?.detail
    error.value = typeof detail === 'string' ? detail : t('admin.invites.errors.create')
  } finally {
    creating.value = false
  }
}

async function revoke(invite: SenderInvite) {
  try {
    await api(`${base.value}/${invite.id}`, { method: 'DELETE' })
    await load()
  } catch {
    show(t('admin.invites.errors.revoke'), 'error')
  }
}

async function copy(text: string) {
  await navigator.clipboard.writeText(text)
  show(t('admin.common.copied'), 'success')
}

function state(invite: SenderInvite): 'used' | 'expired' | 'pending' {
  if (invite.used_at) return 'used'
  return new Date(invite.expires_at) < new Date() ? 'expired' : 'pending'
}

watch(created, (value) => value && emit('changed'))
</script>

<template>
  <v-dialog v-model="open" max-width="640">
    <v-card>
      <v-card-title>{{ t('admin.invites.title', { channel: connection.display_name }) }}</v-card-title>
      <v-card-text>
        <p class="mb-4 text-ink-900/80">
          {{ connection.channel_type === 'telegram' ? t('admin.invites.helpTelegram') : t('admin.invites.helpCode') }}
        </p>

        <v-alert v-if="created" type="success" variant="tonal" class="mb-4" :title="t('admin.invites.createdTitle', { name: created.label })">
          <template v-if="created.link">
            <p class="mb-2">{{ t('admin.invites.sendLink') }}</p>
            <v-text-field :model-value="created.link" readonly hide-details density="compact" bg-color="surface">
              <template #append-inner>
                <v-btn icon="mdi-content-copy" size="small" variant="text" :aria-label="t('admin.common.copy')" @click="copy(created.link!)" />
              </template>
            </v-text-field>
            <p class="mt-2 text-sm">{{ t('admin.invites.orCode', { code: created.code }) }}</p>
          </template>
          <template v-else>
            <p class="mb-2">{{ t('admin.invites.sendCode', { channel: connection.display_name }) }}</p>
            <div class="flex items-center gap-2">
              <code class="rounded bg-surface-0 px-3 py-1 text-lg font-bold tracking-widest">{{ created.code }}</code>
              <v-btn icon="mdi-content-copy" size="small" variant="text" :aria-label="t('admin.common.copy')" @click="copy(created.code)" />
            </div>
          </template>
          <p class="mt-2 text-sm">{{ t('admin.invites.once', { date: formatDateTime(created.expires_at) }) }}</p>
        </v-alert>

        <form class="flex items-start gap-2" @submit.prevent="create">
          <v-text-field v-model="label" :label="t('admin.invites.forWhom')" :hint="t('admin.invites.forWhomHint')" persistent-hint density="compact" />
          <v-btn type="submit" color="primary" :loading="creating" :disabled="!label.trim()">{{ t('admin.invites.create') }}</v-btn>
        </form>
        <v-alert v-if="error" type="error" variant="tonal" density="compact" class="mt-3">{{ error }}</v-alert>

        <h3 v-if="invites.length" class="mb-2 mt-6 font-display font-bold">{{ t('admin.invites.list') }}</h3>
        <v-list v-if="invites.length" density="compact">
          <v-list-item v-for="invite in invites" :key="invite.id" :title="invite.label">
            <v-list-item-subtitle>
              {{ t(`admin.invites.state.${state(invite)}`, { date: formatDateTime(invite.used_at ?? invite.expires_at) }) }}
            </v-list-item-subtitle>
            <template #append>
              <v-btn v-if="state(invite) === 'pending'" size="small" variant="text" @click="revoke(invite)">{{ t('admin.invites.revoke') }}</v-btn>
            </template>
          </v-list-item>
        </v-list>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="open = false">{{ t('admin.common.close') }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
