<script setup lang="ts">
import type { Company } from '~/types'

const { t } = useI18n()
const api = useApi()
const { show } = useSnackbar()

const timezones = Intl.supportedValuesOf('timeZone')
// Written here, not in the template: its braces would close the template's own {{ }}.
const LOGO_TAG = '{{ branding.logo }}'
const company = ref<Company | null>(null)
const loadError = ref('')
const saving = ref(false)
const logoUrl = ref<string | null>(null)
const logoFile = ref<File | null>(null)
const uploading = ref(false)
const form = ref<{ validate: () => Promise<{ valid: boolean }> } | null>(null)
const required = (v: string) => Boolean(v?.trim()) || t('admin.common.validation.required')

async function loadLogo() {
  if (logoUrl.value) URL.revokeObjectURL(logoUrl.value)
  logoUrl.value = null
  if (!company.value?.has_logo) return
  try {
    logoUrl.value = URL.createObjectURL(await api<Blob>('/company/logo', { responseType: 'blob' }))
  } catch {
    // The rest of the page works without the picture.
  }
}

async function load() {
  try {
    company.value = await api<Company>('/company')
    await loadLogo()
  } catch {
    loadError.value = t('admin.settings.company.errors.load')
  }
}

async function save() {
  if (!company.value || !(await form.value?.validate())?.valid) return
  saving.value = true
  try {
    const { name, language, timezone, brand_color } = company.value
    company.value = await api<Company>('/company', { method: 'PATCH', body: { name, language, timezone, brand_color } })
    show(t('admin.settings.saved'), 'success')
  } catch {
    show(t('admin.settings.company.errors.save'), 'error')
  } finally {
    saving.value = false
  }
}

async function uploadLogo() {
  if (!logoFile.value) return
  uploading.value = true
  try {
    const body = new FormData()
    body.append('file', logoFile.value)
    company.value = await api<Company>('/company/logo', { method: 'PUT', body })
    logoFile.value = null
    await loadLogo()
    show(t('admin.settings.company.logoSaved'), 'success')
  } catch (err) {
    const detail = (err as { data?: { detail?: unknown } })?.data?.detail
    show(typeof detail === 'string' ? detail : t('admin.settings.company.errors.logo'), 'error')
  } finally {
    uploading.value = false
  }
}

async function removeLogo() {
  try {
    company.value = await api<Company>('/company/logo', { method: 'DELETE' })
    await loadLogo()
  } catch {
    show(t('admin.settings.company.errors.logo'), 'error')
  }
}

onMounted(load)
onBeforeUnmount(() => {
  if (logoUrl.value) URL.revokeObjectURL(logoUrl.value)
})
</script>

<template>
  <div>
    <v-alert v-if="loadError" type="error" variant="tonal">{{ loadError }}</v-alert>
    <v-progress-linear v-else-if="!company" indeterminate color="primary" />
    <template v-else>
      <v-form ref="form" @submit.prevent="save">
        <v-text-field v-model="company.name" :label="t('admin.settings.company.name')" :rules="[required]" />
        <div class="grid gap-4 md:grid-cols-2">
          <v-select
            v-model="company.language"
            :items="[{ value: 'es', title: 'Español' }, { value: 'en', title: 'English' }]"
            :label="t('admin.settings.company.language')"
            :hint="t('admin.settings.company.languageHint')"
            persistent-hint
          />
          <v-autocomplete v-model="company.timezone" :items="timezones" :label="t('admin.settings.company.timezone')" />
        </div>
        <div class="mt-4 flex items-center gap-3">
          <label for="brand-color" class="text-sm">{{ t('admin.settings.company.color') }}</label>
          <input
            id="brand-color"
            :value="company.brand_color ?? '#C0432A'"
            type="color"
            class="h-9 w-14 cursor-pointer rounded border border-slate-300"
            @input="company.brand_color = ($event.target as HTMLInputElement).value"
          >
          <span class="text-sm text-ink-900/70">{{ t('admin.settings.company.colorHint') }}</span>
        </div>
        <div class="mt-4 flex justify-end">
          <v-btn type="submit" color="primary" :loading="saving">{{ t('admin.common.save') }}</v-btn>
        </div>
      </v-form>

      <v-divider class="my-6" />
      <h3 class="font-display text-lg font-bold">{{ t('admin.settings.company.logo') }}</h3>
      <p class="mb-4 text-sm text-ink-900/70">{{ t('admin.settings.company.logoHint', { tag: LOGO_TAG }) }}</p>
      <div class="flex flex-wrap items-center gap-6">
        <div class="flex h-24 w-56 items-center justify-center rounded border border-slate-300 bg-surface-0 p-2">
          <img v-if="logoUrl" :src="logoUrl" :alt="t('admin.settings.company.logo')" class="max-h-full max-w-full">
          <span v-else class="text-sm text-ink-900/60">{{ t('admin.settings.company.noLogo') }}</span>
        </div>
        <div class="flex min-w-[260px] flex-1 items-start gap-2">
          <v-file-input
            v-model="logoFile"
            accept="image/png,image/jpeg,image/webp"
            :label="t('admin.settings.company.logoUpload')"
            prepend-icon="mdi-image-outline"
            density="compact"
            hide-details
          />
          <v-btn color="primary" variant="tonal" :disabled="!logoFile" :loading="uploading" @click="uploadLogo">
            {{ t('admin.settings.company.upload') }}
          </v-btn>
          <v-btn v-if="company.has_logo" variant="text" color="failed" @click="removeLogo">{{ t('admin.settings.company.removeLogo') }}</v-btn>
        </div>
      </div>
    </template>
  </div>
</template>
