<script setup lang="ts">
import { useDisplay } from 'vuetify'

const { t, te } = useI18n()
const route = useRoute()
const authStore = useAuthStore()

// Every panel tab used to carry the landing's title; now each says which page it is (FE-11).
useHead({
  title: () => (route.meta.titleKey ? `${t(route.meta.titleKey)} · ReportAI` : 'ReportAI')
})
const { state: snackbar } = useSnackbar()

const { isAdmin, isSuperAdmin, isInstanceAdmin } = useRole()

const navItems = computed(() => {
  const settings = { title: t('admin.layout.nav.settings'), to: '/admin/settings', icon: 'mdi-cog-outline' }
  if (isSuperAdmin.value) {
    return [
      { title: t('admin.layout.nav.tenants'), to: '/admin/tenants', icon: 'mdi-domain' },
      ...(isInstanceAdmin.value ? [settings] : [])
    ]
  }
  const items = [
    { title: t('admin.dashboard.title'), to: '/dashboard', icon: 'mdi-home-outline' },
    { title: t('admin.layout.nav.reports'), to: '/admin/reports', icon: 'mdi-file-chart-outline' }
  ]
  if (!isAdmin.value) return items
  return [
    ...items,
    { title: t('admin.layout.nav.documentTypes'), to: '/admin/document-types', icon: 'mdi-file-document-outline' },
    { title: t('admin.layout.nav.channels'), to: '/admin/channels', icon: 'mdi-message-processing-outline' },
    { title: t('admin.layout.nav.team'), to: '/admin/team', icon: 'mdi-account-multiple-outline' },
    { title: t('admin.layout.nav.usage'), to: '/admin/usage', icon: 'mdi-chart-line' },
    settings
  ]
})

const roleLabel = computed(() => {
  const key = `admin.roles.${authStore.user?.role}`
  return te(key) ? t(key) : authStore.user?.role
})

// A security advisory that affects this release is shown on every page to whoever can update it.
const { status: updates, load: loadUpdates } = useUpdates()
onMounted(() => {
  if (isInstanceAdmin.value) loadUpdates()
})

const { mobile } = useDisplay()
// null lets Vuetify open it on a desktop and keep it closed on a phone. Forcing it open made the
// server — which can't know the screen size — render a phone's dark scrim that stayed over the page.
const drawer = ref<boolean | null>(null)
function toggleDrawer() {
  drawer.value = !(drawer.value ?? !mobile.value)
}
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
      <v-app-bar-nav-icon :aria-label="t('admin.layout.toggleMenu')" @click="toggleDrawer" />
      <v-app-bar-title>
        <v-btn variant="text" to="/profile" prepend-icon="mdi-account-circle-outline" class="text-none">
          {{ authStore.user?.full_name }}
        </v-btn>
      </v-app-bar-title>
      <v-spacer />
      <v-chip class="mr-4" size="small" variant="tonal">{{ roleLabel }}</v-chip>
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
          {{ t('admin.layout.demoBanner') }}
        </v-alert>
        <v-alert
          v-if="isInstanceAdmin && updates?.advisories.length"
          type="error"
          variant="tonal"
          class="mb-6"
          :title="t('admin.updates.securityTitle')"
        >
          {{ t('admin.updates.securityBody', { version: updates.current, fixed: updates.advisories[0]?.fixed_in }) }}
          <template #append>
            <v-btn variant="text" to="/admin/settings?tab=updates">{{ t('admin.updates.howTo') }}</v-btn>
          </template>
        </v-alert>
        <slot />
      </v-container>
    </v-main>

    <v-snackbar v-model="snackbar.visible" :color="snackbar.color" location="bottom right">
      {{ snackbar.text }}
    </v-snackbar>
  </v-app>
</template>
