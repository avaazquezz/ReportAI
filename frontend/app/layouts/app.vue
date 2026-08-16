<script setup lang="ts">
const { t } = useI18n()
const authStore = useAuthStore()
const { state: snackbar } = useSnackbar()

const navItems = computed(() => {
  if (authStore.user?.role === 'super_admin') {
    return [{ title: 'Empresas', to: '/admin/tenants', icon: 'mdi-domain' }]
  }
  return [
    { title: 'Tipos de documento', to: '/admin/document-types', icon: 'mdi-file-document-outline' },
    { title: 'Canales', to: '/admin/channels', icon: 'mdi-message-processing-outline' },
    { title: 'Informes', to: '/admin/reports', icon: 'mdi-file-chart-outline' },
    { title: 'Uso y coste', to: '/admin/usage', icon: 'mdi-chart-line' }
  ]
})

const drawer = ref(true)
</script>

<template>
  <v-app>
    <v-navigation-drawer v-model="drawer" color="surface" border>
      <v-list-item to="/dashboard" class="py-4">
        <span class="font-display text-lg font-bold text-ink-900">ReportAI</span>
      </v-list-item>
      <v-divider />
      <v-list nav density="comfortable">
        <v-list-item
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          :prepend-icon="item.icon"
          :title="item.title"
        />
      </v-list>
    </v-navigation-drawer>

    <v-app-bar color="surface" flat border>
      <v-app-bar-nav-icon @click="drawer = !drawer" />
      <v-app-bar-title>{{ authStore.user?.full_name }}</v-app-bar-title>
      <v-spacer />
      <v-chip class="mr-4" size="small" variant="tonal">{{ authStore.user?.role }}</v-chip>
      <LanguageSwitcher class="mr-4" />
      <v-btn variant="text" @click="authStore.logout()">{{ t('admin.layout.logout') }}</v-btn>
    </v-app-bar>

    <v-main>
      <v-container fluid class="max-w-[1400px] py-8">
        <v-alert
          v-if="authStore.user?.is_demo"
          type="info"
          variant="tonal"
          density="compact"
          class="mb-6"
        >
          Modo demo — solo lectura. Envía una nota de voz al bot de Telegram y verás el informe
          aparecer aquí.
        </v-alert>
        <slot />
      </v-container>
    </v-main>

    <v-snackbar v-model="snackbar.visible" :color="snackbar.color" location="bottom right">
      {{ snackbar.text }}
    </v-snackbar>
  </v-app>
</template>
