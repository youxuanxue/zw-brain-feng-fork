<script setup lang="ts">
import { computed } from 'vue';
import { toasts, dismissToast } from '@/composables/useActionStub';

const list = computed(() => toasts.value);
</script>

<template>
  <div class="toast-stack" role="status" aria-live="polite">
    <div
      v-for="t in list"
      :key="t.id"
      :class="['toast', `toast-${t.kind}`]"
      @click="dismissToast(t.id)"
    >
      <strong>{{ t.title }}</strong>
      <span v-if="t.detail" class="toast-detail">{{ t.detail }}</span>
    </div>
  </div>
</template>

<style scoped>
.toast-stack {
  position: fixed;
  top: auto;
  right: 24px;
  bottom: 24px;
  display: grid;
  gap: 8px;
  z-index: 9999;
  max-width: 380px;
  pointer-events: none;
}
.toast {
  padding: 12px 14px;
  border-radius: 8px;
  border: 1px solid;
  background: #fff;
  cursor: pointer;
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.06);
  display: grid;
  gap: 4px;
  font-size: 13px;
  pointer-events: auto;
}
.toast strong { font-weight: 600; }
.toast-detail { color: var(--b-muted, #5c6370); font-size: 12px; }
.toast-info  { border-color: #d4e2f4; color: #0048a8; background: #f2f7fd; }
.toast-ok    { border-color: #9ad29a; color: #1f5e1f; background: #effaee; }
.toast-warn  { border-color: #f0c674; color: #6b4f00; background: #fff8e6; }
.toast-error { border-color: #f0a3a3; color: #7a1a1a; background: #fbeeee; }

@media (max-width: 640px) {
  .toast-stack {
    right: 12px;
    bottom: 12px;
    left: 12px;
    max-width: none;
    gap: 6px;
  }
  .toast {
    padding: 10px 12px;
    font-size: 12px;
  }
  .toast-detail {
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
}
</style>
