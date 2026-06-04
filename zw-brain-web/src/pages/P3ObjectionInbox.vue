<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import { authFetch } from '@/composables/useAuth';
import { getProductRole } from '@/composables/useProductRole';
import { formatTodoStatus, todoStatusTone } from '@/lib/statusLabels';
import { shortId } from '@/lib/userLanguage';
import { OBJECTION_TYPE_ZH, formatObjectionType } from '@/lib/objectionLabels';
import { apiUrl } from '@/composables/useApiBase';

interface ObjectionRow {
  id: string;
  title: string;
  status: string;
  targetType: string;
  targetId: string;
  createdAt: string;
  updatedAt: string;
}

type SortKey = 'id' | 'title' | 'targetType' | 'targetId' | 'status' | 'createdAt' | 'updatedAt';
type SortDir = 'asc' | 'desc';

const TYPE_OPTIONS = Object.keys(OBJECTION_TYPE_ZH);
const STATUS_OPTIONS = [
  'submitted',
  'accepted',
  'platform_investigating',
  'provider_investigating',
  'escalated',
  'resolved',
  'closed',
  'rejected',
];

const items = ref<ObjectionRow[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);

const filterType = ref<string>('');
const filterStatus = ref<string>('');
const sortKey = ref<SortKey>('createdAt');
const sortDir = ref<SortDir>('desc');

function formatTime(iso: string): string {
  if (!iso) return '—';
  const m = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})/.exec(iso);
  return m ? `${m[1]} ${m[2]}` : iso;
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const resp = await authFetch(apiUrl('/api/skills/objection.case.query'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ role: getProductRole().value, confirmed: true }),
    });
    if (!resp.ok) throw new Error('暂时无法加载异议列表，请稍后再试。');
    const payload = (await resp.json()) as { items?: Record<string, unknown>[] };
    items.value = (payload.items ?? []).map((row) => ({
      id: String(row.id ?? ''),
      title: String(row.title ?? row.topic ?? '—'),
      status: String(row.status ?? ''),
      targetType: String(row.target_type ?? row.targetType ?? '—'),
      targetId: String(row.target_id ?? row.targetId ?? '—'),
      createdAt: String(row.created_at ?? row.createdAt ?? ''),
      updatedAt: String(row.updated_at ?? row.updatedAt ?? ''),
    }));
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

onMounted(() => { void load(); });

const filtered = computed(() => {
  let rows = items.value;
  if (filterType.value) rows = rows.filter((r) => r.targetType === filterType.value);
  if (filterStatus.value) rows = rows.filter((r) => r.status === filterStatus.value);
  return rows;
});

const sorted = computed(() => {
  const rows = [...filtered.value];
  const k = sortKey.value;
  const dir = sortDir.value === 'asc' ? 1 : -1;
  rows.sort((a, b) => {
    const va = (a[k] ?? '') as string;
    const vb = (b[k] ?? '') as string;
    return va < vb ? -1 * dir : va > vb ? 1 * dir : 0;
  });
  return rows;
});

function toggleSort(k: SortKey) {
  if (sortKey.value === k) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc';
  } else {
    sortKey.value = k;
    sortDir.value = 'asc';
  }
}

function sortIcon(k: SortKey): string {
  if (sortKey.value !== k) return '⇅';
  return sortDir.value === 'asc' ? '↑' : '↓';
}

const headerMeta = computed(() => {
  if (loading.value) return '正在加载……';
  if (error.value) return `加载失败：${error.value}`;
  const total = items.value.length;
  const shown = filtered.value.length;
  if (!total) return '暂无异议，可发起新异议';
  return shown === total ? `${total} 条异议记录` : `${shown} / ${total} 条（已筛选）`;
});

function clearFilters() {
  filterType.value = '';
  filterStatus.value = '';
}
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

      <div v-if="!loading && items.length" class="filter-bar">
        <label class="filter-field">
          <span>类型</span>
          <select v-model="filterType">
            <option value="">全部</option>
            <option v-for="t in TYPE_OPTIONS" :key="t" :value="t">{{ formatObjectionType(t) }}</option>
          </select>
        </label>
        <label class="filter-field">
          <span>状态</span>
          <select v-model="filterStatus">
            <option value="">全部</option>
            <option v-for="s in STATUS_OPTIONS" :key="s" :value="s">{{ formatTodoStatus(s) }}</option>
          </select>
        </label>
        <button
          v-if="filterType || filterStatus"
          type="button"
          class="filter-clear"
          @click="clearFilters"
        >清除筛选</button>
      </div>

      <table v-if="!loading && sorted.length" class="focus-table">
        <thead>
          <tr>
            <th class="th-sort" @click="toggleSort('id')">编号 <span class="sort-icon">{{ sortIcon('id') }}</span></th>
            <th class="th-sort" @click="toggleSort('title')">标题 <span class="sort-icon">{{ sortIcon('title') }}</span></th>
            <th class="th-sort" @click="toggleSort('targetType')">类型 <span class="sort-icon">{{ sortIcon('targetType') }}</span></th>
            <th class="th-sort" @click="toggleSort('targetId')">对象 <span class="sort-icon">{{ sortIcon('targetId') }}</span></th>
            <th class="th-sort" @click="toggleSort('status')">状态 <span class="sort-icon">{{ sortIcon('status') }}</span></th>
            <th class="th-sort" @click="toggleSort('createdAt')">提交时间 <span class="sort-icon">{{ sortIcon('createdAt') }}</span></th>
            <th class="th-sort" @click="toggleSort('updatedAt')">更新时间 <span class="sort-icon">{{ sortIcon('updatedAt') }}</span></th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="it in sorted" :key="it.id">
            <td><code>{{ shortId(it.id) }}</code></td>
            <td>{{ it.title }}</td>
            <td>{{ formatObjectionType(it.targetType) }}</td>
            <td><code class="target-id">{{ shortId(it.targetId) }}</code></td>
            <td><span class="status-pill" :class="todoStatusTone(it.status)">{{ formatTodoStatus(it.status) }}</span></td>
            <td>{{ formatTime(it.createdAt) }}</td>
            <td>{{ formatTime(it.updatedAt) }}</td>
            <td><a :href="`#/request-flow/objection/${it.id}`" class="row-link">跟踪</a></td>
          </tr>
        </tbody>
      </table>
      <p v-else-if="!loading && items.length" class="focus-empty">当前筛选无匹配记录。<a href="#" @click.prevent="clearFilters">清除筛选</a></p>
      <p v-else-if="!loading" class="focus-empty">暂无异议记录。<a href="#/request-flow/objection/new">发起第一条异议</a></p>
    </section>
  </main>
</template>

<style scoped>
.row-link { color: var(--b-primary, #006be6); font-size: 13px; text-decoration: none; }
.row-link:hover { text-decoration: underline; }
.filter-bar {
  display: flex; gap: 16px; align-items: center; padding: 12px 0;
  border-bottom: 1px solid var(--b-border-subtle, #eef1f5);
  margin-bottom: 8px;
}
.filter-field {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 13px; color: var(--b-text-secondary, #555);
}
.filter-field select {
  padding: 4px 8px; border: 1px solid var(--b-border, #d0d7e2); border-radius: 4px;
  font-size: 13px; background: #fff; cursor: pointer; min-width: 96px;
}
.filter-clear {
  font-size: 12px; padding: 4px 10px; cursor: pointer;
  border: 1px solid var(--b-border, #d0d7e2); border-radius: 4px;
  background: #fff; color: var(--b-text-secondary, #555);
}
.filter-clear:hover { background: #f5f7fa; }
.th-sort { cursor: pointer; user-select: none; white-space: nowrap; }
.th-sort:hover { background: var(--b-hover, #f5f7fa); }
.sort-icon {
  font-size: 11px; color: var(--b-text-tertiary, #98a2b3);
  margin-left: 2px; font-weight: normal;
}
.target-id { font-size: 12px; color: var(--b-text-secondary, #555); }
</style>
