<script setup lang="ts">
import type { TokenResponse } from '~/types'

definePageMeta({
  layout: 'auth',
  titleKey: 'auth.signup.title',
  // Only the hosted service lets anyone sign up (SIGNUP_ENABLED); elsewhere the API says 404.
  // defineNuxtRouteMiddleware keeps Nuxt's context after the await (Nuxt restores it for a bare
  // function under `middleware`, not inside an array): without it the server-side redirect is a 500.
  middleware: [
    defineNuxtRouteMiddleware(async () => {
      if (!(await useInstance().load())?.signup_enabled) return navigateTo('/login')
    })
  ]
})

const route = useRoute()
// The emailed link brings the form back, sealed: what is left is choosing a password.
const token = String(route.query.token ?? '')
const { t, locale } = useI18n()
const api = useApi()
const authStore = useAuthStore()

const company = ref('')
const fullName = ref('')
const email = ref('')
const acceptedTerms = ref(false)
const website = ref('') // the honeypot: hidden from people, filled by bots
const sent = ref(false)

const password = ref('')
const confirmPassword = ref('')
const accountExists = ref(false)

const error = ref('')
const loading = ref(false)

const status = (err: unknown) => (err as { response?: Response }).response?.status

async function onSignUp() {
  error.value = ''
  loading.value = true
  try {
    await api('/signup', {
      method: 'POST',
      body: {
        company: {
          name: company.value,
          language: locale.value === 'en' ? 'en' : 'es',
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'Europe/Madrid'
        },
        full_name: fullName.value,
        email: email.value,
        accepted_terms: acceptedTerms.value,
        website: website.value
      }
    })
    sent.value = true
  } catch (err) {
    error.value = t(status(err) === 429 ? 'auth.signup.errors.tooMany' : 'auth.signup.errors.send')
  } finally {
    loading.value = false
  }
}

async function onComplete() {
  error.value = ''
  if (password.value.length < 8) {
    error.value = t('auth.resetPassword.errors.tooShort')
    return
  }
  if (password.value !== confirmPassword.value) {
    error.value = t('auth.resetPassword.errors.mismatch')
    return
  }
  loading.value = true
  try {
    const tokens = await api<TokenResponse>('/signup/complete', {
      method: 'POST',
      body: { token, password: password.value }
    })
    await authStore.applySession(tokens)
    await navigateTo('/dashboard')
  } catch (err) {
    accountExists.value = status(err) === 409
    error.value = t(accountExists.value ? 'auth.signup.errors.exists' : 'auth.signup.errors.invalidLink')
  } finally {
    loading.value = false
  }
}

const inputClass =
  'mt-1 w-full rounded-md border border-slate-300 bg-surface-0 px-3 py-2 font-body text-ink-900 focus:border-capture-500 focus:outline-none focus:ring-1 focus:ring-capture-500'
const labelClass = 'font-body text-sm font-medium text-ink-900'
const buttonClass =
  'w-full rounded-md bg-capture-600 px-4 py-2.5 font-body text-sm font-semibold text-white transition-transform hover:scale-[1.01] disabled:opacity-60'
</script>

<template>
  <div class="mx-auto flex max-w-md flex-col justify-center px-6 py-24">
    <h1 class="font-display text-2xl font-bold text-ink-900">
      {{ token ? t('auth.signup.completeTitle') : t('auth.signup.title') }}
    </h1>

    <form v-if="token" class="mt-8 space-y-5" @submit.prevent="onComplete">
      <div>
        <label for="password" :class="labelClass">{{ t('auth.resetPassword.newPasswordLabel') }}</label>
        <input id="password" v-model="password" type="password" required autocomplete="new-password" :class="inputClass">
      </div>
      <div>
        <label for="confirmPassword" :class="labelClass">{{ t('auth.resetPassword.confirmPasswordLabel') }}</label>
        <input
          id="confirmPassword"
          v-model="confirmPassword"
          type="password"
          required
          autocomplete="new-password"
          :class="inputClass"
        >
      </div>
      <p v-if="error" class="font-body text-sm text-red-600" role="alert">
        {{ error }}
        <NuxtLink :to="accountExists ? '/login' : '/signup'" class="font-medium text-capture-600">
          {{ accountExists ? t('auth.signup.goToLogin') : t('auth.signup.again') }}
        </NuxtLink>
      </p>
      <button type="submit" :disabled="loading" :class="buttonClass">
        {{ loading ? t('auth.signup.creating') : t('auth.signup.complete') }}
      </button>
    </form>

    <div v-else-if="sent" class="mt-8 rounded-md border border-slate-300 bg-surface-0 p-6">
      <p class="font-body text-sm text-ink-900">{{ t('auth.signup.sent', { email }) }}</p>
      <NuxtLink to="/login" class="mt-4 inline-block font-body text-sm font-medium text-capture-600">
        {{ t('auth.signup.goToLogin') }}
      </NuxtLink>
    </div>

    <form v-else class="mt-8 space-y-5" @submit.prevent="onSignUp">
      <p class="font-body text-sm text-ink-900/70">{{ t('auth.signup.intro') }}</p>
      <div>
        <label for="company" :class="labelClass">{{ t('auth.signup.companyLabel') }}</label>
        <input id="company" v-model="company" type="text" required maxlength="255" autocomplete="organization" :class="inputClass">
      </div>
      <div>
        <label for="fullName" :class="labelClass">{{ t('auth.signup.nameLabel') }}</label>
        <input id="fullName" v-model="fullName" type="text" required maxlength="255" autocomplete="name" :class="inputClass">
      </div>
      <div>
        <label for="email" :class="labelClass">{{ t('auth.login.emailLabel') }}</label>
        <input id="email" v-model="email" type="email" required maxlength="255" autocomplete="email" :class="inputClass">
      </div>
      <div class="absolute -left-[10000px] h-px w-px overflow-hidden" aria-hidden="true">
        <label for="website">Website</label>
        <input id="website" v-model="website" type="text" tabindex="-1" autocomplete="off">
      </div>
      <label class="flex items-start gap-2 font-body text-sm text-ink-900">
        <input v-model="acceptedTerms" type="checkbox" required class="mt-1">
        <i18n-t keypath="auth.signup.terms" tag="span" scope="global">
          <template #terms>
            <NuxtLink to="/aviso-legal" class="font-medium text-capture-600">{{ t('auth.signup.termsLink') }}</NuxtLink>
          </template>
        </i18n-t>
      </label>
      <p v-if="error" class="font-body text-sm text-red-600" role="alert">{{ error }}</p>
      <button type="submit" :disabled="loading" :class="buttonClass">
        {{ loading ? t('auth.signup.submitting') : t('auth.signup.submit') }}
      </button>
      <NuxtLink to="/login" class="block text-center font-body text-sm text-ink-900/70 hover:text-capture-600">
        {{ t('auth.signup.haveAccount') }}
      </NuxtLink>
    </form>
  </div>
</template>
