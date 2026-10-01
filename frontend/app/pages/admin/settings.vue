<script setup lang="ts">
definePageMeta({
  layout: 'app',
  titleKey: 'admin.layout.nav.settings',
  middleware: [
    'auth',
    async () => {
      // Composables first: after an await there is no Nuxt context to resolve them in.
      const instance = useInstance()
      const { isAdmin, isInstanceAdmin } = useRole()
      await instance.load()
      if (!isAdmin.value && !isInstanceAdmin.value) return navigateTo('/dashboard')
    }
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
        <SettingsCompanySettings v-if="tab === 'company'" />
        <SettingsAiSettings v-else-if="tab === 'ai'" />
        <SettingsEmailSettings v-else-if="tab === 'email'" />
        <SettingsUpdatesPanel v-else-if="tab === 'updates'" />
      </v-card-text>
    </v-card>
  </div>
</template>
