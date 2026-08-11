<script setup lang="ts">
definePageMeta({ middleware: ['auth', 'require-tenant-admin'], layout: 'app' })

const { items, total, loading, error, fetchList, create } = useDocumentTypes()
const { show } = useSnackbar()
const router = useRouter()

const headers = [
  { title: 'Nombre', key: 'name' },
  { title: 'Descripción', key: 'description' },
  { title: 'Estado', key: 'is_active' },
  { title: '', key: 'actions', sortable: false, width: '1%' }
]

const createDialog = ref(false)
const creating = ref(false)
const createError = ref('')
const form = ref({ name: '', description: '' })

async function onCreate() {
  creating.value = true
  createError.value = ''
  try {
    const result = await create({
      name: form.value.name,
      description: form.value.description || null,
      field_schema: {},
      prompt_instructions: null,
      notification_emails: []
    })
    createDialog.value = false
    form.value = { name: '', description: '' }
    show('Tipo de documento creado.', 'success')
    await router.push(`/admin/document-types/${result.id}`)
  } catch {
    createError.value = 'No se pudo crear. Revisa que el nombre no esté en uso.'
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <div>
    <div class="mb-6 flex items-center justify-between">
      <h1 class="font-display text-2xl font-bold text-ink-900">Tipos de documento</h1>
      <v-btn color="primary" @click="createDialog = true">Nuevo tipo</v-btn>
    </div>

    <AdminResourceTable
      :headers="headers"
      :items="items"
      :total-items="total"
      :loading="loading"
      :error="error"
      @update:options="fetchList"
    >
      <template #item.is_active="{ item }">
        <v-chip :color="item.is_active ? 'approved' : 'failed'" size="small" variant="tonal">
          {{ item.is_active ? 'Activo' : 'Inactivo' }}
        </v-chip>
      </template>
      <template #item.actions="{ item }">
        <v-btn size="small" variant="text" :to="`/admin/document-types/${item.id}`">Editar</v-btn>
      </template>
    </AdminResourceTable>

    <v-dialog v-model="createDialog" max-width="480">
      <v-card>
        <v-card-title>Nuevo tipo de documento</v-card-title>
        <v-card-text>
          <v-form @submit.prevent="onCreate">
            <v-text-field v-model="form.name" label="Nombre" required class="mb-2" />
            <v-textarea v-model="form.description" label="Descripción" rows="2" class="mb-2" />
            <v-alert v-if="createError" type="error" variant="tonal" class="mb-2">{{ createError }}</v-alert>
          </v-form>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="createDialog = false">Cancelar</v-btn>
          <v-btn color="primary" :loading="creating" @click="onCreate">Crear</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>
