<script setup lang="ts">
import { computed } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import { useProvider, useSnapshot } from '@/composables/useSnapshot';
import { deriveFieldDecisions } from '@/lib/providerProjection';
import { formatTodoStatus, todoStatusTone } from '@/lib/statusLabels';
import { shortId } from '@/lib/userLanguage';

const provider = useProvider();
const { source } = useSnapshot();

const items = computed(() => deriveFieldDecisions(provider.value as Record<string, unknown>));

const headerMeta = computed(() => {
  if (source.value !== 'live') return '正在加载……';
  const n = items.value.length;
  if (!n) return '暂无待审核草稿';
  const fromProjection = items.value.some((i) => i.source === 'projection');
  return fromProjection ? `${n} 条待审核` : `${n} 条来自目录待补说明`;
});
</script>

<template>
  <main class="focus-page">
    <section class="panel">
      <PageFocusHeader
        title="反向编目审核收件箱"
        :meta="headerMeta"
        :links="[
          { label: '提供方管理', href: '#/provider' },
          { label: '反向编目向导', href: '#/provider/wizard/reverse-catalog' },
        ]"
      />

      <table v-if="source === 'live' && items.length" class="focus-table">
        <thead>
          <tr><th>编号</th><th>责任单位</th><th>待审核事项</th><th>状态</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="it in items" :key="it.id">
            <td><code>{{ shortId(it.id) }}</code></td>
            <td>{{ it.catalog }}</td>
            <td>{{ it.title }}</td>
            <td><span class="status-pill" :class="todoStatusTone(it.status)">{{ formatTodoStatus(it.status) }}</span></td>
            <td><a :href="`#/provider/inbox/field-decision/${encodeURIComponent(it.id)}`" class="row-link">处理</a></td>
          </tr>
        </tbody>
      </table>

      <p v-else-if="source === 'live'" class="focus-empty">
        暂无待审核草稿。完成反向编目并提交后，待审核事项会出现在此列表。
      </p>
      <p v-else class="focus-empty">等待数据装载……</p>
    </section>
  </main>
</template>

<style scoped>
code { font-size: 12px; background: var(--b-bg-subtle, #e8f2fc); padding: 2px 6px; border-radius: 4px; }
.row-link { font-size: 13px; color: var(--b-primary, #006be6); text-decoration: none; }
.status-pill { font-size: 12px; padding: 2px 8px; border-radius: 999px; }
.tone-warn { background: #fff7e6; color: #ad6800; }
.tone-ok { background: #f6ffed; color: #389e0d; }
.tone-neutral { background: var(--b-bg-subtle, #e8f2fc); color: var(--b-muted, #5c6370); }
</style>
