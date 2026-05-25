<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import { authFetch } from '@/composables/useAuth';
import { getProductRole } from '@/composables/useProductRole';
import { formatTodoStatus, todoStatusTone } from '@/lib/statusLabels';

interface ObjectionRow {
  id: string;
  title: string;
  status: string;
  targetType: string;
  targetId: string;
}

const items = ref<ObjectionRow[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const resp = await authFetch('/api/skills/objection.case.query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ role: getProductRole().value, confirmed: true }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const payload = (await resp.json()) as { items?: Record<string, unknown>[] };
    items.value = (payload.items ?? []).map((row) => ({
      id: String(row.id ?? ''),
      title: String(row.title ?? row.topic ?? '—'),
      status: String(row.status ?? ''),
      targetType: String(row.target_type ?? row.targetType ?? '—'),
      targetId: String(row.target_id ?? row.targetId ?? '—'),
    }));
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

onMounted(() => { void load(); });

const headerMeta = computed(() => {
  if (loading.value) return '正在加载……';
  if (error.value) return `加载失败：${error.value}`;
  return items.value.length ? `${items.value.length} 条异议记录` : '暂无异议，可发起新异议';
});
</script>

<template>
  <main class="focus-page">
    <nav class="crumbs"><a href="#/request-flow">← 申请与跟踪</a></nav>
    <section class="panel">
      <PageFocusHeader
        title="我的异议"
        :meta="headerMeta"
        :links="[{ label: '发起异议', href: '#/request-flow/objection/new' }]"
      />
      <table v-if="!loading && items.length" class="focus-table">
        <thead>
          <tr><th>编号</th><th>标题</th><th>对象</th><th>状态</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="it in items" :key="it.id">
            <td><code>{{ it.id }}</code></td>
            <td>{{ it.title }}</td>
            <td>{{ it.targetType }} · {{ it.targetId }}</td>
            <td><span class="status-pill" :class="todoStatusTone(it.status)">{{ formatTodoStatus(it.status) }}</span></td>
            <td><a :href="`#/request-flow/objection/${it.id}`" class="row-link">跟踪</a></td>
          </tr>
        </tbody>
      </table>
      <p v-else-if="!loading" class="focus-empty">暂无异议记录。<a href="#/request-flow/objection/new">发起第一条异议</a></p>
    </section>
  </main>
</template>

<style scoped>
.row-link { color: var(--b-primary, #006be6); font-size: 13px; text-decoration: none; }
.row-link:hover { text-decoration: underline; }
</style>
