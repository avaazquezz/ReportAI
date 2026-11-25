<script setup lang="ts">
// An AI assistant (claude.ai, ChatGPT, Cursor) asks to use ReportAI as the person signed in: the API
// sent their browser here with the request sealed in `?request=` (backend/app/services/oauth). They
// approve or deny, and the browser goes back to the app with the answer. Rendered in the browser
// only (nuxt.config.ts): the app sends the browser from another site, and the session cookies are
// SameSite=Strict, so a server render would not see that the person is signed in.
import type { OAuthConsent, OAuthConsentRedirect } from '~/types'

definePageMeta({ middleware: ['auth'], layout: 'auth', titleKey: 'auth.consent.title' })

const { t } = useI18n()
const api = useApi()
const route = useRoute()
const authStore = useAuthStore()

const sealed = computed(() => (typeof route.query.request === 'string' ? route.query.request : ''))
const consent = ref<OAuthConsent | null>(null)
const loading = ref(true)
const error = ref('')
const answering = ref<'approve' | 'deny' | null>(null)

const statusOf = (err: unknown) => (err as { response?: Response }).response?.status

// What a 404 means depends on it: the API's public OAuth metadata is a 404 only while OAuth is off.
async function oauthIsOn(): Promise<boolean> {
  try {
    await api('/oauth/metadata')
    return true
  } catch (err) {
    // Any other failure can't tell: the 404 reads as an expired request, as it most often is.
    return statusOf(err) !== 404
  }
}

// The failed request explained (utils/consentFailure.ts), or, if the session ended, a sign-in that
// brings the person back here with the app's request.
async function explain(err: unknown) {
  const status = statusOf(err)
  const failure = consentFailure(status, status === 404 ? await oauthIsOn() : true)
  if (failure === 'signIn') {
    await navigateTo({ path: '/login', query: { next: route.fullPath } })
    return
  }
  error.value = t(`auth.consent.errors.${failure}`)
}

onMounted(async () => {
  if (!sealed.value) {
    error.value = t('auth.consent.errors.expired')
    loading.value = false
    return
  }
  try {
    consent.value = await api<OAuthConsent>('/oauth/consent', { query: { request: sealed.value } })
  } catch (err) {
    await explain(err)
  } finally {
    loading.value = false
  }
})

async function answer(approve: boolean) {
  answering.value = approve ? 'approve' : 'deny'
  error.value = ''
  try {
    const { redirect_to } = await api<OAuthConsentRedirect>('/oauth/consent', {
      method: 'POST',
      body: { request: sealed.value, approve }
    })
    // Out of the panel and back to the app, with the code or the refusal: a full navigation.
    window.location.assign(redirect_to)
  } catch (err) {
    await explain(err)
    answering.value = null
  }
}

const buttonClass = 'w-full rounded-md px-4 py-2.5 font-body text-sm font-semibold transition-transform hover:scale-[1.01] disabled:opacity-60'
</script>

<template>
  <div class="mx-auto flex max-w-md flex-col justify-center px-6 py-24">
    <p v-if="loading" class="font-body text-ink-900/70" role="status">{{ t('auth.consent.loading') }}</p>

    <template v-else-if="consent">
      <h1 class="break-words font-display text-2xl font-bold text-ink-900">
        {{ t('auth.consent.heading', { app: consent.client_name }) }}
      </h1>
      <p v-if="authStore.user" class="mt-2 break-words font-body text-sm text-ink-900/70">
        {{ t('auth.consent.signedInAs', { email: authStore.user.email }) }}
      </p>

      <div class="mt-6 rounded-md border border-slate-300 bg-surface-0 px-4 py-3 font-body text-sm">
        <p class="m-0 font-semibold">{{ t('auth.consent.can.title') }}</p>
        <ul class="mb-0 mt-1 list-disc pl-5">
          <li>{{ t('auth.consent.can.read') }}</li>
          <li>{{ t('auth.consent.can.draft') }}</li>
        </ul>
        <p class="mb-0 mt-3 font-semibold">{{ t('auth.consent.cannot.title') }}</p>
        <ul class="mb-0 mt-1 list-disc pl-5">
          <li>{{ t('auth.consent.cannot.send') }}</li>
          <li>{{ t('auth.consent.cannot.more') }}</li>
        </ul>
      </div>

      <p class="mt-4 break-words font-body text-sm text-ink-900/80">
        {{ t('auth.consent.returnsTo') }} <span class="font-mono font-semibold">{{ consent.redirect_host }}</span>
      </p>
      <p v-if="consent.published_by" class="mt-2 break-words font-body text-sm text-ink-900/80">
        {{ t('auth.consent.publishedBy') }} <span class="font-mono font-semibold">{{ consent.published_by }}</span>
      </p>
      <p v-else class="mt-2 font-body text-sm text-ink-900/80">{{ t('auth.consent.selfRegistered') }}</p>
      <p class="mt-2 font-body text-sm text-ink-900/70">{{ t('auth.consent.onlyYours') }}</p>

      <p v-if="error" class="mt-4 font-body text-sm text-red-600" role="alert">{{ error }}</p>
      <div class="mt-6 flex flex-col gap-3">
        <button type="button" :disabled="answering !== null" :class="[buttonClass, 'bg-capture-600 text-white']" @click="answer(true)">
          {{ answering === 'approve' ? t('auth.consent.approving') : t('auth.consent.approve') }}
        </button>
        <button
          type="button"
          :disabled="answering !== null"
          :class="[buttonClass, 'border border-slate-300 bg-surface-0 text-ink-900']"
          @click="answer(false)"
        >
          {{ t('auth.consent.deny') }}
        </button>
      </div>
    </template>

    <template v-else>
      <h1 class="font-display text-2xl font-bold text-ink-900">{{ t('auth.consent.title') }}</h1>
      <p class="mt-4 font-body text-ink-900/80" role="alert">{{ error }}</p>
      <NuxtLink to="/dashboard" class="mt-6 font-body text-sm text-capture-600 hover:underline">{{ t('auth.consent.toPanel') }}</NuxtLink>
    </template>
  </div>
</template>
