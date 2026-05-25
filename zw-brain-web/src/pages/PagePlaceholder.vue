<script setup lang="ts">
import { useRoute } from 'vue-router';
import PageFocusHeader from '@/components/PageFocusHeader.vue';

const route = useRoute();
const title = String(route.meta.title ?? route.path);
</script>

<template>
  <main class="focus-page">
    <section class="panel">
      <PageFocusHeader :title="title" meta="功能建设中" :links="[{ label: '工作台', href: '#/workbench' }]" />
      <p class="focus-empty">路径 <code>#{{ route.path }}</code></p>
    </section>
  </main>
</template>

<style scoped>
code { font-size: 12px; background: var(--b-bg-subtle, #e8f2fc); padding: 2px 6px; border-radius: 4px; }
</style>
