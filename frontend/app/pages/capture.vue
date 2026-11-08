<script setup lang="ts">
definePageMeta({
  middleware: [
    'auth',
    () => {
      if (!useRole().canCapture.value) return navigateTo('/dashboard')
    }
  ],
  layout: 'app',
  titleKey: 'admin.capture.title'
})

interface CaptureDocumentType {
  id: string
  name: string
  description: string | null
}

const MAX_PHOTOS = 10

const { t } = useI18n()
const api = useApi()
const authStore = useAuthStore()
const { formatDateTime } = useLocaleDate()
const { items: queued, enqueue, retry, discard } = useCaptureQueue()

const types = ref<CaptureDocumentType[] | null>(null)
const loadError = ref(false)
const documentTypeId = ref<string | null>(null)

const recording = ref(false)
const audio = ref<Blob | null>(null)
const audioUrl = ref<string | null>(null)
// Chrome's webm says nothing of its length, so the player would show 0:00: the recorder's count does.
const audioSeconds = ref(0)
const text = ref('')
const photos = ref<{ file: File; url: string }[]>([])
const photoInput = ref<HTMLInputElement | null>(null)

const sending = ref(false)
// One id per capture, kept until the queue has it: sending again after a failure to store reuses
// it, so the server's Idempotency-Key can never turn one recording into two reports.
let captureId = crypto.randomUUID()
const outcome = ref<{ type: 'info' | 'error'; message: string } | null>(null)
const toDiscard = ref<string | null>(null)

const typeName = (id: string) => types.value?.find((type) => type.id === id)?.name ?? t('admin.reports.noType')
const canSend = computed(
  () => !!documentTypeId.value && (!!audio.value || !!text.value.trim()) && !recording.value && !sending.value
)

onMounted(async () => {
  const copy = `capture-types:${authStore.user!.id}`
  const kept = readOfflineCopy<CaptureDocumentType[]>(copy)
  try {
    // With a copy to fall back on, one bar of coverage isn't waited out (a GET: safe to abandon).
    const wait = kept ? { timeout: DEVICE_COPY_AFTER_MS, retry: 0 } : {}
    types.value = await api<CaptureDocumentType[]>('/capture/document-types', wait)
    keepOfflineCopy(copy, types.value)
  } catch (error) {
    // No coverage: the types this person last saw are the ones they can record now.
    if (!kept || !isUnreachable(error)) {
      loadError.value = true
      return
    }
    types.value = kept
  }
  if (types.value.length === 1) documentTypeId.value = types.value[0]!.id
})

function setAudio(blob: Blob | null, seconds = 0) {
  audioSeconds.value = seconds
  if (audioUrl.value) URL.revokeObjectURL(audioUrl.value)
  audio.value = blob
  audioUrl.value = blob ? URL.createObjectURL(blob) : null
}

function addPhotos(event: Event) {
  const input = event.target as HTMLInputElement
  for (const file of Array.from(input.files ?? []).slice(0, MAX_PHOTOS - photos.value.length)) {
    photos.value.push({ file, url: URL.createObjectURL(file) })
  }
  input.value = '' // the same picture can be picked again after removing it
}

function removePhoto(index: number) {
  URL.revokeObjectURL(photos.value[index]!.url)
  photos.value.splice(index, 1)
}

function reset() {
  setAudio(null)
  text.value = ''
  photos.value.forEach((photo) => URL.revokeObjectURL(photo.url))
  photos.value = []
}

async function send() {
  if (!canSend.value || !documentTypeId.value) return
  sending.value = true
  outcome.value = null
  const id = captureId
  try {
    // Stored on the phone first: nothing recorded is lost if the upload can't happen now.
    const result = await enqueue({
      id,
      documentTypeId: documentTypeId.value,
      text: text.value.trim() || null,
      audio: audio.value,
      photos: photos.value.map((photo) => photo.file)
    })
    captureId = crypto.randomUUID()
    if (result.state === 'sent') {
      reset()
      await navigateTo(`/admin/reports/${id}`)
      return
    }
    reset()
    outcome.value =
      result.state === 'queued'
        ? { type: 'info', message: t('admin.capture.queuedOffline') }
        : { type: 'error', message: result.error ?? t('admin.capture.errors.send') }
  } catch {
    // Not even stored (private browsing can block IndexedDB): keep the form so nothing is lost.
    outcome.value = { type: 'error', message: t('admin.capture.errors.store') }
  } finally {
    sending.value = false
  }
}

onBeforeUnmount(reset)
</script>

<template>
  <div class="mx-auto max-w-xl">
    <h1 class="mb-6 font-display text-2xl font-bold text-ink-900">{{ t('admin.capture.title') }}</h1>

    <v-alert v-if="loadError" type="error" variant="tonal">{{ t('admin.capture.errors.types') }}</v-alert>
    <v-skeleton-loader v-else-if="!types" type="list-item, image" />
    <v-alert v-else-if="!types.length" type="info" variant="tonal">{{ t('admin.capture.noTypes') }}</v-alert>

    <form v-else class="flex flex-col gap-6" @submit.prevent="send">
      <v-select
        v-if="types.length > 1"
        v-model="documentTypeId"
        :items="types"
        item-title="name"
        item-value="id"
        :label="t('admin.capture.type')"
        :hint="types.find((type) => type.id === documentTypeId)?.description ?? undefined"
        persistent-hint
      />
      <p v-else class="font-body text-sm text-ink-900/70">{{ t('admin.capture.typeOnly', { name: types[0]!.name }) }}</p>

      <div class="flex flex-col items-center gap-3">
        <RecordControl v-if="!audio" v-model:recording="recording" :disabled="sending" @recorded="setAudio" />
        <template v-else>
          <p class="font-body text-sm text-ink-900/70">{{ t('admin.capture.recordedFor', { length: formatDuration(audioSeconds) }) }}</p>
          <audio :src="audioUrl ?? undefined" controls class="w-full" :aria-label="t('admin.capture.recorded')" />
          <v-btn variant="text" prepend-icon="mdi-microphone" @click="setAudio(null)">{{ t('admin.capture.recordAgain') }}</v-btn>
        </template>
      </div>

      <v-textarea
        v-model="text"
        :label="audio ? t('admin.capture.notes') : t('admin.capture.text')"
        rows="3"
        auto-grow
        counter="20000"
        maxlength="20000"
      />

      <div>
        <input ref="photoInput" type="file" accept="image/*" capture="environment" multiple class="hidden" @change="addPhotos">
        <div class="grid grid-cols-3 gap-2">
          <div v-for="(photo, index) in photos" :key="photo.url" class="relative aspect-square overflow-hidden rounded bg-paper-100">
            <img :src="photo.url" :alt="t('admin.capture.photo', { n: index + 1 })" class="h-full w-full object-cover">
            <v-btn
              icon="mdi-close"
              size="x-small"
              class="!absolute right-1 top-1"
              :aria-label="t('admin.capture.removePhoto', { n: index + 1 })"
              @click="removePhoto(index)"
            />
          </div>
        </div>
        <v-btn
          v-if="photos.length < MAX_PHOTOS"
          variant="tonal"
          prepend-icon="mdi-camera-outline"
          class="mt-2"
          :disabled="sending"
          @click="photoInput?.click()"
        >
          {{ t('admin.capture.addPhoto') }}
        </v-btn>
      </div>

      <v-alert v-if="outcome" :type="outcome.type" variant="tonal" role="alert">{{ outcome.message }}</v-alert>

      <v-btn type="submit" color="primary" size="x-large" block :disabled="!canSend" :loading="sending">
        {{ t('admin.capture.send') }}
      </v-btn>
    </form>

    <section v-if="queued.length" class="mt-10" :aria-label="t('admin.capture.queue.title')">
      <h2 class="mb-1 font-display text-lg font-bold text-ink-900">{{ t('admin.capture.queue.title') }}</h2>
      <p class="mb-3 font-body text-sm text-ink-900/70">{{ t('admin.capture.queue.help') }}</p>
      <v-list lines="two" density="compact" class="rounded border">
        <v-list-item v-for="item in queued" :key="item.id">
          <v-list-item-title>{{ typeName(item.documentTypeId) }}</v-list-item-title>
          <v-list-item-subtitle>
            {{ formatDateTime(new Date(item.createdAt).toISOString()) }} ·
            {{ item.state === 'failed' ? item.error ?? t('admin.capture.queue.failed') : t(`admin.capture.queue.${item.state}`) }}
          </v-list-item-subtitle>
          <template v-if="item.state === 'failed'" #append>
            <v-btn size="small" variant="text" @click="retry(item.id)">{{ t('admin.capture.queue.retry') }}</v-btn>
            <v-btn size="small" variant="text" color="failed" @click="toDiscard = item.id">{{ t('admin.capture.queue.discard') }}</v-btn>
          </template>
        </v-list-item>
      </v-list>
    </section>

    <AdminConfirmDialog
      :model-value="toDiscard !== null"
      :title="t('admin.capture.queue.discardTitle')"
      :message="t('admin.capture.queue.discardMessage')"
      :confirm-text="t('admin.capture.queue.discard')"
      confirm-color="failed"
      @update:model-value="toDiscard = null"
      @confirm="toDiscard && discard(toDiscard)"
    />
  </div>
</template>
