<script setup lang="ts">
import { computed } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import { useProvider, useSnapshot } from '@/composables/useSnapshot';
import { formatTodoStatus, todoStatusTone } from '@/lib/statusLabels';

const provider = useProvider();
const { source } = useSnapshot();

type InboxRow = { id: string; title: string; status: string };

const items = computed((): InboxRow[] => {
  const raw = (provider.value as { objection_cases?: unknown[] }).objection_cases;
  if (!Array.isArray(raw)) return [];
  return raw.map((row) => {
    const it = row as Record<string, unknown>;
    return {
      id: String(it.id ?? ''),
      title: String(it.title ?? it.id ?? ''),
      status: String(it.status ?? ''),
    };
  });
});

const headerMeta = computed(() => {
  if (source.value !== 'live') return '正在加载……';
  const n = items.value.length;
  return n ? `${n} 条待响应异议` : '暂无待响应异议';
});
</script>

<template>
  <main class="focus-page">
    <nav class="crumbs"><a href="#/provider">← 提供方管理</a></nav>
    <section class="panel">
      <PageFocusHeader title="异议响应收件箱" :meta="headerMeta" />

      <table v-if="source === 'live' && items.length" class="focus-table">
        <thead>
          <tr><th>异议编号</th><th>标题</th><th>状态</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="it in items" :key="it.id">
            <td><code>{{ it.id }}</code></td>
            <td>{{ it.title }}</td>
            <td><span :class="todoStatusTone(it.status)">{{ formatTodoStatus(it.status) }}</span></td>
            <td><a :href="`#/provider/inbox/objection/${it.id}`">响应</a></td>
          </tr>
        </tbody>
      </table>
      <p v-else-if="source === 'live'" class="focus-empty">暂无待响应异议</p>
      <p v-else class="focus-empty">等待数据装载……</p>
    </section>
  </main>
</template>
