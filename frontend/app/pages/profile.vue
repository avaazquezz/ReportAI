<script setup lang="ts">
import type { TokenResponse, User } from '~/types'

definePageMeta({ middleware: 'auth', layout: 'app', titleKey: 'admin.profile.title' })

const { t } = useI18n()
const api = useApi()
const { show } = useSnackbar()
const authStore = useAuthStore()

type FormRef = { validate: () => Promise<{ valid: boolean }>; reset: () => void } | null
const required = (v: string) => Boolean(v?.trim()) || t('admin.common.validation.required')

const fullName = ref(authStore.user?.full_name ?? '')
const nameForm = ref<FormRef>(null)
const savingName = ref(false)

async function saveName() {
  if (!(await nameForm.value?.validate())?.valid) return
  savingName.value = true
  try {
    authStore.user = await api<User>('/auth/me', { method: 'PATCH', body: { full_name: fullName.value } })
    show(t('admin.profile.nameSaved'), 'success')
  } catch {
    show(t('admin.profile.errors.name'), 'error')
  } finally {
    savingName.value = false
  }
}

const passwords = reactive({ current: '', next: '', confirm: '' })
const passwordForm = ref<FormRef>(null)
const savingPassword = ref(false)
const passwordError = ref('')
const minLength = (v: string) => (v ?? '').length >= 8 || t('admin.profile.validation.length')
const matches = (v: string) => v === passwords.next || t('admin.profile.validation.match')

async function changePassword() {
  if (!(await passwordForm.value?.validate())?.valid) return
  savingPassword.value = true
  passwordError.value = ''
  try {
    const tokens = await api<TokenResponse>('/auth/change-password', {
      method: 'POST',
      body: { current_password: passwords.current, new_password: passwords.next }
    })
    // The new password ends every other session; this one carries on with fresh tokens.
    await authStore.applySession(tokens)
    passwordForm.value?.reset()
    show(t('admin.profile.passwordSaved'), 'success')
  } catch (err) {
    const status = (err as { response?: Response }).response?.status
    passwordError.value = status === 400 ? t('admin.profile.errors.current') : t('admin.profile.errors.password')
  } finally {
    savingPassword.value = false
  }
}
</script>

<template>
  <div class="max-w-2xl">
    <h1 class="mb-6 font-display text-2xl font-bold text-ink-900">{{ t('admin.profile.title') }}</h1>

    <v-card rounded="lg" elevation="0" border class="mb-6 pa-6">
      <h2 class="mb-4 font-display text-lg font-bold">{{ t('admin.profile.account') }}</h2>
      <p class="mb-4 text-sm text-ink-900/70">{{ authStore.user?.email }}</p>
      <v-form ref="nameForm" @submit.prevent="saveName">
        <v-text-field v-model="fullName" :label="t('admin.common.nameLabel')" :rules="[required]" autocomplete="name" />
        <div class="flex justify-end">
          <v-btn type="submit" color="primary" :loading="savingName">{{ t('admin.common.save') }}</v-btn>
        </div>
      </v-form>
    </v-card>

    <v-card rounded="lg" elevation="0" border class="pa-6">
      <h2 class="mb-1 font-display text-lg font-bold">{{ t('admin.profile.password') }}</h2>
      <p class="mb-4 text-sm text-ink-900/70">{{ t('admin.profile.passwordHelp') }}</p>
      <v-form ref="passwordForm" @submit.prevent="changePassword">
        <v-text-field v-model="passwords.current" :label="t('admin.profile.current')" type="password" :rules="[required]" autocomplete="current-password" />
        <div class="grid gap-4 md:grid-cols-2">
          <v-text-field v-model="passwords.next" :label="t('admin.profile.new')" type="password" :rules="[minLength]" autocomplete="new-password" />
          <v-text-field v-model="passwords.confirm" :label="t('admin.profile.confirm')" type="password" :rules="[matches]" autocomplete="new-password" />
        </div>
        <v-alert v-if="passwordError" type="error" variant="tonal" density="compact" class="mb-4">{{ passwordError }}</v-alert>
        <div class="flex justify-end">
          <v-btn type="submit" color="primary" :loading="savingPassword">{{ t('admin.profile.change') }}</v-btn>
        </div>
      </v-form>
    </v-card>
  </div>
</template>
