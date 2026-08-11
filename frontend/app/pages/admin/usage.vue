<script setup lang="ts">
definePageMeta({ middleware: ['auth', 'require-tenant-admin'], layout: 'app' })
</script>

<template>
  <div>
    <h1 class="mb-6 font-display text-2xl font-bold text-ink-900">Uso y coste</h1>
    <AdminUsageSummary />
  </div>
</template>
