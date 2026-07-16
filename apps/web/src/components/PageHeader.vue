<template>
  <div class="page-heading">
    <div>
      <p v-if="eyebrow" class="page-eyebrow">{{ eyebrow }}</p>
      <h1>{{ title }}</h1>
      <p v-if="description" class="page-description">{{ description }}</p>
    </div>
    <div v-if="$slots.actions" class="page-actions"><slot name="actions" /></div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ title: string; eyebrow?: string; description?: string }>()
</script>
