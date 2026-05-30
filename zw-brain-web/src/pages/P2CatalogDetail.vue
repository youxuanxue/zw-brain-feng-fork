<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import { useCatalogResources } from '@/composables/useCatalogResources';
import { getProductRole } from '@/composables/useProductRole';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import ResourceCard from '@/components/ResourceCard.vue';

const route = useRoute();
const code = computed(() => String(route.params.code ?? ''));
const role = getProductRole();
const { catalog, resources, total, loading, fetchError, source } = useCatalogResources(
  () => code.value,
  role.value,
);

const headerTitle = computed(() => {
  if (catalog.value?.title) return String(catalog.value.title);
  if (loading.value) return '正在加载……';
  return code.value;
});

const headerMeta = computed(() => {
  if (fetchError.value) return `加载失败：${fetchError.value}`;
  if (loading.value || source.value !== 'live') return '正在加载目录资源……';
  return total.value ? `${total.value} 个关联资源` : '该目录暂无关联资源';
});
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/discovery/catalog-browse">← 目录浏览</a></nav>
    <section class="panel">
      <PageFocusHeader :title="headerTitle" :meta="headerMeta" />
      <div v-if="resources.length" class="card-grid">
        <ResourceCard v-for="r in resources" :key="String(r.id ?? '')" :resource="r" />
      </div>
      <p v-else-if="!loading && source === 'live'" class="focus-empty">该目录暂无关联资源。</p>
      <p v-else class="focus-empty">正在加载目录资源……</p>
    </section>
  </main>
</template>

<style scoped>
.card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 12px; margin-top: 8px; }
.focus-empty { font-size: 14px; color: var(--b-muted, #5c6370); margin: 16px 0 0; }
</style>
