<script setup lang="ts">
import { useRoute } from 'vue-router';
import PageFocusHeader from '@/components/PageFocusHeader.vue';

const route = useRoute();
const title = String(route.meta.title ?? route.path);
// meta 文案来自路由 meta.note（按页诚实说明），缺省给一句对未开放模块成立的诚实话；
// 空泛套话由 scripts/check_no_placeholder_word.py 守卫拦截，此处一律写诚实文案。
const note = String(route.meta.note ?? '该模块按交付计划推进，当前暂未开放。');
</script>

<template>
  <main class="focus-page">
    <section class="panel">
      <PageFocusHeader :title="title" :meta="note" :links="[{ label: '工作台', href: '#/workbench' }]" />
      <p class="focus-empty">路径 <code>#{{ route.path }}</code></p>
    </section>
  </main>
</template>

<style scoped>
code { font-size: 12px; background: var(--b-bg-subtle, #e8f2fc); padding: 2px 6px; border-radius: 4px; }
</style>
