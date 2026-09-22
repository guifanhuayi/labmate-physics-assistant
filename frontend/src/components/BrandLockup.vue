<script setup lang="ts">
defineProps<{ compact?: boolean }>()
</script>

<template>
  <div class="brand-lockup" :class="{ compact }">
    <span class="brand-mark" aria-hidden="true">λ</span>
    <span>
      <strong>LabMate</strong>
      <small v-if="!compact">物理实验数字助手</small>
    </span>
  </div>
</template>
