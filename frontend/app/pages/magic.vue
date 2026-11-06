<script setup lang="ts">
// A technician's way in. With ?token= (the emailed link) it signs in when they tap the button,
// never on page load: mail scanners open links to check them and would spend the token. Without
// it, they ask for a link and type its code — what the app installed on an iPhone needs, since
// a link opens in Safari, not in the installed app.
definePageMeta({ layout: 'auth', titleKey: 'auth.magic.title' })

const authStore = useAuthStore()
const route = useRoute()
const { t } = useI18n()

const token = computed(() => (typeof route.query.token === 'string' ? route.query.token : ''))
const email = ref('')
const code = ref('')
const requested = ref(false)
const error = ref('')
const loading = ref(false)

async function signIn(body: { token: string } | { email: string; code: string }) {
  error.value = ''
  loading.value = true
  try {
    await authStore.magicSignIn(body)
    await navigateTo('/admin/reports')
  } catch {
    error.value = t('auth.magic.error')
  } finally {
    loading.value = false
  }
}

async function requestLink() {
  error.value = ''
  loading.value = true
  try {
    await authStore.requestMagicLink(email.value)
    requested.value = true
  } catch {
    error.value = t('auth.magic.requestError')
  } finally {
    loading.value = false
  }
}

const inputClass =
  'mt-1 w-full rounded-md border border-slate-300 bg-surface-0 px-3 py-2 font-body text-ink-900 focus:border-capture-500 focus:outline-none focus:ring-1 focus:ring-capture-500'
const buttonClass =
  'w-full rounded-md bg-capture-600 px-4 py-2.5 font-body text-sm font-semibold text-white transition-transform hover:scale-[1.01] disabled:opacity-60'
</script>

<template>
  <div class="mx-auto flex max-w-md flex-col justify-center px-6 py-24">
    <h1 class="font-display text-2xl font-bold text-ink-900">{{ t('auth.magic.title') }}</h1>

    <template v-if="token">
      <p class="mt-4 font-body text-ink-900/80">{{ t('auth.magic.fromLink') }}</p>
      <button type="button" :disabled="loading" :class="[buttonClass, 'mt-8']" @click="signIn({ token })">
        {{ loading ? t('auth.magic.signingIn') : t('auth.magic.signIn') }}
      </button>
    </template>

    <form v-else-if="!requested" class="mt-8 space-y-5" @submit.prevent="requestLink">
      <p class="font-body text-ink-900/80">{{ t('auth.magic.askHelp') }}</p>
      <div>
        <label for="magic-email" class="font-body text-sm font-medium text-ink-900">{{ t('auth.login.emailLabel') }}</label>
        <input id="magic-email" v-model="email" type="email" required autocomplete="email" :class="inputClass">
      </div>
      <button type="submit" :disabled="loading" :class="buttonClass">{{ t('auth.magic.send') }}</button>
    </form>

    <form v-else class="mt-8 space-y-5" @submit.prevent="signIn({ email, code })">
      <p class="font-body text-ink-900/80" role="status">{{ t('auth.magic.sent', { email }) }}</p>
      <div>
        <label for="magic-code" class="font-body text-sm font-medium text-ink-900">{{ t('auth.magic.codeLabel') }}</label>
        <input
          id="magic-code"
          v-model="code"
          required
          autocomplete="one-time-code"
          autocapitalize="characters"
          spellcheck="false"
          placeholder="ABCD-EFGH"
          :class="[inputClass, 'font-mono tracking-widest uppercase']"
        >
      </div>
      <button type="submit" :disabled="loading" :class="buttonClass">
        {{ loading ? t('auth.magic.signingIn') : t('auth.magic.signIn') }}
      </button>
      <button
        type="button"
        class="block w-full cursor-pointer border-0 bg-transparent text-center font-body text-sm text-ink-900/70 hover:text-capture-600"
        @click="requested = false"
      >
        {{ t('auth.magic.again') }}
      </button>
    </form>

    <p v-if="error" class="mt-4 font-body text-sm text-red-600" role="alert">{{ error }}</p>
  </div>
</template>
