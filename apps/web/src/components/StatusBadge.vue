<template>
  <span class="status-badge" :class="`status-${status.toLowerCase()}`">{{ statusLabels[status] }}</span>
</template>

<script setup lang="ts">
import { statusLabels } from '@/config/labels'
import type { IncidentStatus } from '@/types/domain'

defineProps<{ status: IncidentStatus }>()
</script>
