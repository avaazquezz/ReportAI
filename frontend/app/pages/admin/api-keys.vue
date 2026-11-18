<script setup lang="ts">
import type { ApiKey, ApiKeyCreated } from '~/types'

definePageMeta({ middleware: ['auth', 'require-company-user'], layout: 'app', titleKey: 'admin.layout.nav.apiKeys' })

const { t } = useI18n()
const api = useApi()
const config = useRuntimeConfig()
const { show } = useSnackbar()
const { isAdmin } = useRole()
const { formatDate, formatDateTime } = useLocaleDate()

const NAME_MAX = 100 // ApiKeyCreate.name on the backend

// Only the browser knows the page's origin, which a relative API base (production's /api) needs.
const connectUrl = ref('')
const keyPlaceholder = computed(() => `<${t('admin.apiKeys.connect.yourKey')}>`)
const claudeAppSteps = computed(() => [
  t('admin.apiKeys.connect.steps.open'),
  t('admin.apiKeys.connect.steps.name'),
  t('admin.apiKeys.connect.steps.auth'),
  t('admin.apiKeys.connect.steps.header', { value: `Bearer ${keyPlaceholder.value}` })
])

const keys = ref<ApiKey[]>([])
const loading = ref(false)
const loadError = ref('')

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    keys.value = await api<ApiKey[]>('/api-keys')
  } catch {
    loadError.value = t('admin.apiKeys.errors.load')
  } finally {
    loading.value = false
  }
}
onMounted(() => {
  connectUrl.value = mcpUrl(config.public.apiBase, window.location.origin)
  load()
})

function errorText(err: unknown, fallback: string) {
  const status = (err as { response?: Response }).response?.status
  // The read-only public demo account: the API refuses every change it asks for.
  if (status === 403) return t('admin.apiKeys.errors.readOnly')
  // Creating answers 400 for one reason only: the person's cap on active keys.
  return status === 400 ? t('admin.apiKeys.errors.limit') : fallback
}

async function copy(text: string) {
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    // No clipboard over plain HTTP (an installation reached by its IP) or without permission;
    // the text stays on screen to copy by hand.
    show(t('admin.apiKeys.errors.copy'), 'error')
    return
  }
  show(t('admin.common.copied'), 'success')
}

// ── Creating ───────────────────────────────────────────────────────────────────────────
type FormRef = { validate: () => Promise<{ valid: boolean }>; resetValidation: () => void } | null
const createForm = ref<FormRef>(null)
const name = ref('')
const creating = ref(false)
const createError = ref('')
// The secret exists only here, until the dialog that shows it closes: the API keeps just its hash.
const created = ref<ApiKeyCreated | null>(null)
const required = (v: string) => Boolean(v?.trim()) || t('admin.common.validation.required')
const short = (v: string) => (v ?? '').trim().length <= NAME_MAX || t('admin.apiKeys.create.maxLength', { max: NAME_MAX })

async function createKey() {
  if (!(await createForm.value?.validate())?.valid) return
  creating.value = true
  createError.value = ''
  try {
    created.value = await api<ApiKeyCreated>('/api-keys', { method: 'POST', body: { name: name.value.trim() } })
    name.value = ''
    createForm.value?.resetValidation()
    await load()
  } catch (err) {
    createError.value = errorText(err, t('admin.apiKeys.errors.create'))
  } finally {
    creating.value = false
  }
}

// ── Revoking ───────────────────────────────────────────────────────────────────────────
const confirmDialog = ref(false)
const pending = ref<ApiKey | null>(null)

async function revoke() {
  const key = pending.value
  if (!key) return
  try {
    await api(`/api-keys/${key.id}`, { method: 'DELETE' })
    show(t('admin.apiKeys.toast.revoked', { name: key.name }), 'success')
  } catch (err) {
    show(errorText(err, t('admin.apiKeys.errors.revoke')), 'error')
  }
  await load()
}
</script>

<template>
  <div class="max-w-3xl">
    <h1 class="mb-2 font-display text-2xl font-bold text-ink-900">{{ t('admin.layout.nav.apiKeys') }}</h1>
    <p class="mb-6 text-ink-900/70">{{ t('admin.apiKeys.help') }}</p>

    <v-card rounded="lg" elevation="0" border class="mb-6 pa-6">
      <h2 class="mb-4 font-display text-lg font-bold">{{ t('admin.apiKeys.connect.title') }}</h2>
      <v-text-field :model-value="connectUrl" :label="t('admin.apiKeys.connect.url')" readonly hide-details density="compact" class="font-mono">
        <template #append-inner>
          <v-btn icon="mdi-content-copy" size="small" variant="text" :aria-label="t('admin.apiKeys.copy.url')" :disabled="!connectUrl" @click="copy(connectUrl)" />
        </template>
      </v-text-field>

      <h3 class="mb-1 mt-6 font-display font-bold">{{ t('admin.apiKeys.connect.claudeCode') }}</h3>
      <p class="mb-2 text-sm text-ink-900/70">{{ t('admin.apiKeys.connect.claudeCodeHelp') }}</p>
      <pre v-if="connectUrl" class="m-0 whitespace-pre-wrap break-all rounded bg-paper-100 px-3 py-2 text-sm">{{ claudeCodeCommand(connectUrl, keyPlaceholder) }}</pre>

      <h3 class="mb-2 mt-6 font-display font-bold">{{ t('admin.apiKeys.connect.claudeApp') }}</h3>
      <ol class="m-0 list-decimal pl-5 text-sm">
        <li v-for="step in claudeAppSteps" :key="step" class="mb-1">{{ step }}</li>
      </ol>
      <p class="mb-0 mt-3 text-sm text-ink-900/70">{{ t('admin.apiKeys.connect.note') }}</p>
    </v-card>

    <v-card rounded="lg" elevation="0" border class="mb-6 pa-6">
      <h2 class="mb-1 font-display text-lg font-bold">{{ t('admin.apiKeys.create.title') }}</h2>
      <p class="mb-4 text-sm text-ink-900/70">{{ t('admin.apiKeys.create.help') }}</p>
      <v-form ref="createForm" @submit.prevent="createKey">
        <v-text-field
          v-model="name"
          :label="t('admin.common.nameLabel')"
          :placeholder="t('admin.apiKeys.create.placeholder')"
          :rules="[required, short]"
          :counter="NAME_MAX"
        />
        <v-alert v-if="createError" type="error" variant="tonal" density="compact" class="mb-4">{{ createError }}</v-alert>
        <div class="flex justify-end">
          <v-btn type="submit" color="primary" prepend-icon="mdi-key-plus" :loading="creating">{{ t('admin.apiKeys.create.submit') }}</v-btn>
        </div>
      </v-form>
    </v-card>

    <v-card rounded="lg" elevation="0" border>
      <div class="px-6 pb-4 pt-6">
        <h2 class="m-0 font-display text-lg font-bold">{{ isAdmin ? t('admin.apiKeys.list.company') : t('admin.apiKeys.list.mine') }}</h2>
        <p v-if="isAdmin" class="mb-0 mt-1 text-sm text-ink-900/70">{{ t('admin.apiKeys.list.companyHelp') }}</p>
      </div>
      <v-progress-linear v-if="loading" indeterminate color="primary" />
      <v-alert v-if="loadError" type="error" variant="tonal" class="mx-6 mb-6">{{ loadError }}</v-alert>
      <p v-else-if="!loading && !keys.length" class="mb-0 px-6 pb-6 text-ink-900/70">{{ t('admin.apiKeys.list.empty') }}</p>
      <ul v-else class="m-0 list-none p-0">
        <li v-for="key in keys" :key="key.id">
          <v-divider />
          <div class="flex flex-wrap items-center gap-x-4 gap-y-2 px-6 py-3">
            <!-- A revoked key stays listed, greyed out: at 60% the text still reads at 4.5:1. -->
            <div class="min-w-0 flex-1 basis-60" :class="key.revoked_at ? 'text-ink-900/60' : 'text-ink-900'">
              <p class="m-0 break-words font-medium">{{ key.name }}</p>
              <p class="m-0 text-sm" :class="{ 'text-ink-900/70': !key.revoked_at }">
                <span class="font-mono">{{ key.prefix }}…</span>
                <template v-if="isAdmin"> · {{ t('admin.apiKeys.list.owner', { name: key.owner_name }) }}</template>
              </p>
              <p class="m-0 text-sm" :class="{ 'text-ink-900/70': !key.revoked_at }">
                {{ t('admin.apiKeys.list.created', { date: formatDate(key.created_at) }) }} ·
                {{ key.last_used_at ? t('admin.apiKeys.list.lastUsed', { date: formatDateTime(key.last_used_at) }) : t('admin.apiKeys.list.neverUsed') }}
              </p>
            </div>
            <v-chip size="small" variant="tonal" :color="key.revoked_at ? undefined : 'approved'">
              {{ key.revoked_at ? t('admin.apiKeys.list.revoked', { date: formatDate(key.revoked_at) }) : t('admin.apiKeys.list.active') }}
            </v-chip>
            <v-btn v-if="!key.revoked_at" size="small" variant="text" color="error" @click="pending = key; confirmDialog = true">
              {{ t('admin.apiKeys.list.revoke') }}
            </v-btn>
          </div>
        </li>
      </ul>
    </v-card>

    <!-- Persistent: a stray click outside must not throw away a secret that can't be shown again. -->
    <v-dialog :model-value="!!created" max-width="640" persistent>
      <v-card v-if="created">
        <v-card-title class="whitespace-normal break-words">{{ t('admin.apiKeys.created.title', { name: created.name }) }}</v-card-title>
        <v-card-text>
          <v-alert type="warning" variant="tonal" density="compact" class="mb-4">{{ t('admin.apiKeys.created.once') }}</v-alert>
          <p class="mb-1 text-sm font-semibold">{{ t('admin.apiKeys.created.secret') }}</p>
          <div class="flex items-start gap-1">
            <pre class="m-0 min-w-0 flex-1 whitespace-pre-wrap break-all rounded bg-paper-100 px-3 py-2 text-sm">{{ created.secret }}</pre>
            <v-btn icon="mdi-content-copy" size="small" variant="text" :aria-label="t('admin.apiKeys.copy.key')" @click="copy(created.secret)" />
          </div>
          <p class="mb-1 mt-4 text-sm">{{ t('admin.apiKeys.created.claudeCode') }}</p>
          <div class="flex items-start gap-1">
            <pre class="m-0 min-w-0 flex-1 whitespace-pre-wrap break-all rounded bg-paper-100 px-3 py-2 text-sm">{{ claudeCodeCommand(connectUrl, created.secret) }}</pre>
            <v-btn
              icon="mdi-content-copy"
              size="small"
              variant="text"
              :aria-label="t('admin.apiKeys.copy.command')"
              @click="copy(claudeCodeCommand(connectUrl, created.secret))"
            />
          </div>
          <p class="mb-0 mt-4 text-sm text-ink-900/70">{{ t('admin.apiKeys.created.claudeApp') }}</p>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn color="primary" variant="flat" @click="created = null">{{ t('admin.apiKeys.created.done') }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <AdminConfirmDialog
      v-model="confirmDialog"
      :title="t('admin.apiKeys.confirmRevoke.title')"
      :message="t('admin.apiKeys.confirmRevoke.message', { name: pending?.name })"
      :confirm-text="t('admin.apiKeys.list.revoke')"
      @confirm="revoke"
    />
  </div>
</template>
