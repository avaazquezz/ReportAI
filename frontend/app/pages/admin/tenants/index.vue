<script setup lang="ts">
import type { Tenant } from '~/types'

definePageMeta({ middleware: ['auth', 'require-super-admin'], layout: 'app' })

const { items, total, loading, error, fetchList, create, setActive } = useTenants()
const { show } = useSnackbar()

const headers = [
  { title: 'Nombre', key: 'name' },
  { title: 'Slug', key: 'slug' },
  { title: 'Estado', key: 'is_active' },
  { title: 'Creado', key: 'created_at' },
  { title: '', key: 'actions', sortable: false, width: '1%' }
]

const createDialog = ref(false)
const creating = ref(false)
const createError = ref('')
const form = ref({ name: '', slug: '', admin_email: '', admin_full_name: '' })

const confirmDialog = ref(false)
const pendingTenant = ref<Tenant | null>(null)

function formatDate(value: string) {
  return new Date(value).toLocaleDateString('es-ES', { year: 'numeric', month: 'short', day: 'numeric' })
}

async function onCreate() {
  creating.value = true
  createError.value = ''
  try {
    const result = await create(form.value)
    createDialog.value = false
    form.value = { name: '', slug: '', admin_email: '', admin_full_name: '' }
    show(
      result.invite_email_sent
        ? 'Empresa creada. Invitación enviada.'
        : 'Empresa creada, pero el envío de la invitación falló — puedes reenviarla desde la ficha.',
      result.invite_email_sent ? 'success' : 'error'
    )
    await fetchList({ page: 1, itemsPerPage: 10 })
  } catch {
    createError.value = 'No se pudo crear la empresa. Revisa que el slug no esté en uso.'
  } finally {
    creating.value = false
  }
}

function askToggle(tenant: Tenant) {
  pendingTenant.value = tenant
  confirmDialog.value = true
}

async function confirmToggle() {
  if (!pendingTenant.value) return
  await setActive(pendingTenant.value.id, !pendingTenant.value.is_active)
  show('Estado actualizado.', 'success')
  await fetchList({ page: 1, itemsPerPage: 10 })
}
</script>

<template>
  <div>
    <div class="mb-6 flex items-center justify-between">
      <h1 class="font-display text-2xl font-bold text-ink-900">Empresas</h1>
      <v-btn color="primary" @click="createDialog = true">Nueva empresa</v-btn>
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
          {{ item.is_active ? 'Activa' : 'Inactiva' }}
        </v-chip>
      </template>
      <template #item.created_at="{ item }">
        {{ formatDate(item.created_at) }}
      </template>
      <template #item.actions="{ item }">
        <v-btn size="small" variant="text" :to="`/admin/tenants/${item.id}`">Ver</v-btn>
        <v-btn size="small" variant="text" @click="askToggle(item)">
          {{ item.is_active ? 'Desactivar' : 'Reactivar' }}
        </v-btn>
      </template>
    </AdminResourceTable>

    <v-dialog v-model="createDialog" max-width="480">
      <v-card>
        <v-card-title>Nueva empresa</v-card-title>
        <v-card-text>
          <v-form @submit.prevent="onCreate">
            <v-text-field v-model="form.name" label="Nombre" required class="mb-2" />
            <v-text-field
              v-model="form.slug"
              label="Slug"
              hint="minúsculas, números y guiones"
              persistent-hint
              required
              class="mb-2"
            />
            <v-text-field v-model="form.admin_full_name" label="Nombre del admin" required class="mb-2" />
            <v-text-field v-model="form.admin_email" label="Email del admin" type="email" required class="mb-2" />
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

    <AdminConfirmDialog
      v-model="confirmDialog"
      title="Cambiar estado"
      :message="`¿${pendingTenant?.is_active ? 'Desactivar' : 'Reactivar'} ${pendingTenant?.name}?`"
      confirm-color="primary"
      @confirm="confirmToggle"
    />
  </div>
</template>
