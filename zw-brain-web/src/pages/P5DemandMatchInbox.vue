<script setup lang="ts">
import { computed } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import { useProvider, useSnapshot } from '@/composables/useSnapshot';
import { deriveDemandMatches } from '@/lib/providerProjection';
import { formatTodoStatus, todoStatusTone } from '@/lib/statusLabels';
import { shortId } from '@/lib/userLanguage';

const provider = useProvider();
const { source } = useSnapshot();

const items = computed(() => deriveDemandMatches(provider.value as Record<string, unknown>));

const headerMeta = computed(() => {
  if (source.value !== 'live') return '正在加载……';
  const n = items.value.length;
  if (!n) return '暂无国家平台供需对接';
  const derived = items.value.some((i) => i.source === 'derived');
  return derived ? `${n} 条国家平台需求待对接（由直达资源汇总）` : `${n} 条供需待办`;
});
</script>

<template>
  <main class="focus-page">
    <section class="panel">
      <PageFocusHeader
        title="供需对接收件箱"
        :meta="headerMeta"
        :links="[
          { label: '提供方管理', href: '#/provider' },
          { label: '资源发现', href: '#/discovery' },
        ]"
      />

      <table v-if="source === 'live' && items.length" class="focus-table">
        <thead>
          <tr><th>需求编号</th><th>来源</th><th>标题</th><th>状态</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="it in items" :key="it.id">
            <td><code>{{ shortId(it.id) }}</code></td>
            <td>{{ it.catalog }}</td>
            <td>{{ it.title }}</td>
            <td><span class="status-pill" :class="todoStatusTone(it.status)">{{ formatTodoStatus(it.status) }}</span></td>
            <td><a :href="`#/provider/inbox/demand-match/${encodeURIComponent(it.id)}`" class="row-link">对接</a></td>
          </tr>
        </tbody>
      </table>
      <p v-else-if="source === 'live'" class="focus-empty">暂无国家平台供需需求。</p>
      <p v-else class="focus-empty">等待数据装载……</p>
    </section>
  </main>
</template>

<style scoped>
.row-link { color: var(--b-primary, #006be6); font-size: 13px; }
</style>
