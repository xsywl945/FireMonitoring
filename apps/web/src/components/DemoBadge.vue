<script setup lang="ts">
defineProps<{ synthetic?: boolean }>()
</script>

<template>
  <span class="demo-badge">
    演示模式
    <em v-if="synthetic">合成数据</em>
  </span>
</template>
