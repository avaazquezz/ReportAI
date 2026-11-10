<script setup lang="ts">
definePageMeta({
  layout: 'app',
  titleKey: 'admin.layout.nav.settings',
  middleware: [
    'auth',
    // defineNuxtRouteMiddleware keeps Nuxt's context after the await (Nuxt restores it for a bare
    // function under `middleware`, not inside an array): navigateTo needs it on the server.
    defineNuxtRouteMiddleware(async () => {
      const instance = useInstance()
      const { isAdmin, isInstanceAdmin } = useRole()
      await instance.load()
      if (!isAdmin.value && !isInstanceAdmin.value) return navigateTo('/dashboard')
    })
  ]
})

const { t } = useI18n()
const route = useRoute()
const { isAdmin, isInstanceAdmin } = useRole()

// The company's own settings are its admin's; the installation's (AI keys, mail server,
// updates) belong to whoever runs it.
const tabs = computed(() => [
  ...(isAdmin.value ? [{ value: 'company', title: t('admin.settings.tabs.company') }] : []),
  ...(isInstanceAdmin.value
    ? [
        { value: 'ai', title: t('admin.settings.tabs.ai') },
        { value: 'email', title: t('admin.settings.tabs.email') },
        { value: 'updates', title: t('admin.settings.tabs.updates') }
      ]
    : [])
])
const tab = ref(String(route.query.tab ?? '') || tabs.value[0]?.value)
watch(tab, (value) => navigateTo({ query: { tab: value } }, { replace: true }))

const api = useApi()
const { show } = useSnackbar()
const exporting = ref(false)

async function exportData() {
  exporting.value = true
  try {
    const blob = await api<Blob>('/company/export', { responseType: 'blob' })
    saveBlob(blob, `reportai-export-${new Date().toISOString().slice(0, 10)}.zip`)
  } catch (err) {
    const status = (err as { response?: Response }).response?.status
    show(t(status === 429 ? 'admin.settings.export.tooSoon' : 'admin.settings.export.error'), 'error')
  } finally {
    exporting.value = false
  }
}
</script>

<template>
  <div>
    <h1 class="mb-6 font-display text-2xl font-bold text-ink-900">{{ t('admin.layout.nav.settings') }}</h1>
    <v-card rounded="lg" elevation="0" border>
      <v-tabs v-model="tab" color="primary">
        <v-tab v-for="item in tabs" :key="item.value" :value="item.value">{{ item.title }}</v-tab>
      </v-tabs>
      <v-divider />
      <v-card-text class="pa-6">
        <!-- No v-window: its slide animation stalled half-way while each tab loaded its data. -->
        <template v-if="tab === 'company'">
          <SettingsCompanySettings />
          <template v-if="isAdmin">
            <v-divider class="my-6" />
            <h3 class="font-display text-lg font-bold">{{ t('admin.settings.export.title') }}</h3>
            <p class="mb-4 text-sm text-ink-900/70">{{ t('admin.settings.export.hint') }}</p>
            <v-btn variant="tonal" color="primary" prepend-icon="mdi-download" :loading="exporting" @click="exportData">
              {{ t('admin.settings.export.action') }}
            </v-btn>
            <SettingsDeleteCompany />
          </template>
        </template>
        <SettingsAiSettings v-else-if="tab === 'ai'" />
        <SettingsEmailSettings v-else-if="tab === 'email'" />
        <SettingsUpdatesPanel v-else-if="tab === 'updates'" />
      </v-card-text>
    </v-card>
  </div>
</template>
