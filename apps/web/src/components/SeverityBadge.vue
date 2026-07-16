<template>
  <span class="severity-badge" :class="`severity-${severity.toLowerCase()}`">
    <span class="severity-dot" />
    {{ severityLabels[severity] }}
  </span>
</template>

<script setup lang="ts">
import { severityLabels } from '@/config/labels'
import type { Severity } from '@/types/domain'

defineProps<{ severity: Severity }>()
</script>
