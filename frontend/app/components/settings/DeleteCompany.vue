<script setup lang="ts">
import type { Company } from '~/types'

// Deleting the company blocks everyone in it at once and purges its data after a grace period.
// A one-company installation is deleted by uninstalling it, so it never shows this.
const { t } = useI18n()
const api = useApi()
const authStore = useAuthStore()
const { status } = useInstance()
const { formatDate } = useLocaleDate()

const company = ref<Company | null>(null)
const dialog = ref(false)
const typedName = ref('')
const password = ref('')
const deleting = ref(false)
const error = ref('')
const purgeAfter = ref<string | null>(null)

const nameMatches = computed(() => Boolean(company.value) && typedName.value.trim() === company.value?.name.trim())

onMounted(async () => {
  company.value = await api<Company>('/company')
})

function open() {
  typedName.value = ''
  password.value = ''
  error.value = ''
  dialog.value = true
}

async function confirm() {
  deleting.value = true
  error.value = ''
  try {
    const result = await api<{ purge_after: string }>('/company', {
      method: 'DELETE',
      body: { password: password.value, company_name: typedName.value }
    })
    purgeAfter.value = result.purge_after
  } catch (err) {
    const code = (err as { response?: Response }).response?.status
    error.value = t(code === 429 ? 'admin.settings.delete.tooManyAttempts' : code === 400 ? 'admin.settings.delete.wrongPassword' : 'admin.settings.delete.error')
  } finally {
    deleting.value = false
  }
}
</script>

<template>
  <div v-if="!status?.single_tenant && company">
    <v-divider class="my-6" />
    <h3 class="font-display text-lg font-bold">{{ t('admin.settings.delete.title') }}</h3>
    <p class="mb-4 text-sm text-ink-900/70">{{ t('admin.settings.delete.hint') }}</p>
    <v-btn variant="tonal" color="error" prepend-icon="mdi-delete-forever" @click="open">
      {{ t('admin.settings.delete.action') }}
    </v-btn>

    <v-dialog v-model="dialog" max-width="520" :persistent="Boolean(purgeAfter)">
      <v-card v-if="purgeAfter">
        <v-card-title>{{ t('admin.settings.delete.doneTitle') }}</v-card-title>
        <v-card-text>
          {{ t('admin.settings.delete.done', { date: formatDate(purgeAfter, { year: 'numeric', month: 'long', day: 'numeric' }), email: CONTACT_EMAIL }) }}
        </v-card-text>
        <v-card-actions class="justify-end">
          <v-btn color="primary" @click="authStore.logout()">{{ t('admin.settings.delete.signOut') }}</v-btn>
        </v-card-actions>
      </v-card>
      <v-card v-else>
        <v-card-title>{{ t('admin.settings.delete.title') }}</v-card-title>
        <v-card-text>
          <p class="mb-4">{{ t('admin.settings.delete.warning') }}</p>
          <v-text-field
            v-model="typedName"
            :label="t('admin.settings.delete.nameLabel', { name: company.name })"
            autocomplete="off"
            class="mb-2"
          />
          <v-text-field
            v-model="password"
            :label="t('admin.settings.delete.passwordLabel')"
            type="password"
            autocomplete="current-password"
          />
          <v-alert v-if="error" type="error" variant="tonal" class="mt-2">{{ error }}</v-alert>
        </v-card-text>
        <v-card-actions class="justify-end">
          <v-btn variant="text" @click="dialog = false">{{ t('admin.common.cancel') }}</v-btn>
          <v-btn color="error" :disabled="!nameMatches || !password" :loading="deleting" @click="confirm">
            {{ t('admin.settings.delete.action') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>
