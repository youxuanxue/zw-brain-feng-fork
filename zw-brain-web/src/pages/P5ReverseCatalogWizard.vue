<script setup lang="ts">
import { computed, ref } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import { useProvider, useSnapshot } from '@/composables/useSnapshot';
import { displayRecordName } from '@/lib/userLanguage';
import { mapReverseDraftCatalog } from '@/lib/reverseDraftPayload';
import { providerLifecycleBucket, providerLifecycleLabel } from '@/lib/providerProjection';

interface ResourceRow {
  id: string;
  name: string;
  provider: string;
  catalogued: boolean;
  catalogId: string;
  catalogCode: string;
  statusLabel: string;
}

const { source } = useSnapshot();
const provider = useProvider();

const searchQuery = ref('');
const statusFilter = ref('');
const providerFilter = ref('');

const rawResources = computed<ResourceRow[]>(() => {
  const list = (provider.value.catalogs as unknown[] | undefined) ?? [];
  return list
    .map((c) => {
      const raw = c as Record<string, unknown>;
      const mapped = mapReverseDraftCatalog(raw);
      const lifecycleStatus = raw.lifecycle_status ?? mapped.status;
      return { mapped, lifecycleStatus };
    })
    .filter((c) => c.mapped.schema_ref.trim().length > 0)
    .map((c) => ({
      id: c.mapped.id,
      name: displayRecordName(c.mapped.name, c.mapped.catalog_code, '目录'),
      provider: c.mapped.owner ?? '—',
      catalogued: providerLifecycleBucket(c.lifecycleStatus) === 'published',
      catalogId: c.mapped.id,
      catalogCode: c.mapped.catalog_code,
      statusLabel: providerLifecycleLabel(c.lifecycleStatus),
    }));
});

const providerOptions = computed<string[]>(() => {
  const set = new Set(rawResources.value.map((r) => r.provider).filter((p) => p && p !== '—'));
  return [...set].sort();
});

const filteredResources = computed<ResourceRow[]>(() => {
  let list = rawResources.value;
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.trim().toLowerCase();
    list = list.filter((r) => r.name.toLowerCase().includes(q));
  }
  if (statusFilter.value === 'catalogued') {
    list = list.filter((r) => r.catalogued);
  } else if (statusFilter.value === 'uncatalogued') {
    list = list.filter((r) => !r.catalogued);
  }
  if (providerFilter.value) {
    list = list.filter((r) => r.provider === providerFilter.value);
  }
  return list;
});

const headerMeta = computed(() => {
  if (source.value !== 'live') return '正在加载……';
  const total = rawResources.value.length;
  return total ? `共 ${total} 项可反向编目目录` : '暂无可反向编目目录';
});
</script>

<template>
  <main class="focus-page">
    <nav class="crumbs"><a href="#/provider">← 提供方管理</a></nav>
    <section class="panel">
      <PageFocusHeader
        title="反向编目"
        :meta="headerMeta"
        :links="[{ label: '反向编目审核收件箱', href: '#/provider/inbox/field-decision' }]"
      />

      <template v-if="source === 'live'">
        <div class="filter-bar">
          <input
            v-model="searchQuery"
            type="search"
            class="filter-input"
            placeholder="按目录名称搜索"
          />
          <select v-model="statusFilter" class="filter-select">
            <option value="">全部状态</option>
            <option value="catalogued">已编目</option>
            <option value="uncatalogued">未编目</option>
          </select>
          <select v-model="providerFilter" class="filter-select">
            <option value="">全部提供方</option>
            <option v-for="p in providerOptions" :key="p" :value="p">{{ p }}</option>
          </select>
        </div>

        <table class="data-table">
          <thead>
            <tr>
              <th>数据名称</th>
              <th>提供方</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!filteredResources.length">
              <td colspan="4" class="empty-cell">暂无匹配的目录数据</td>
            </tr>
            <tr v-for="r in filteredResources" :key="r.id">
              <td class="cell-name">{{ r.name }}</td>
              <td>{{ r.provider }}</td>
              <td>
                <span :class="['status-tag', r.catalogued ? 'status-done' : 'status-pending']">
                  {{ r.catalogued ? '已编目' : '未编目' }}
                </span>
                <span class="status-detail">{{ r.statusLabel }}</span>
              </td>
              <td class="cell-actions">
                <a
                  v-if="r.catalogued"
                  :href="`#/provider/catalog/${encodeURIComponent(r.catalogCode)}`"
                  class="action-link"
                >查看目录</a>
                <a
                  v-else
                  :href="`#/provider/wizard/reverse-catalog/detail?catalogId=${encodeURIComponent(r.catalogId)}`"
                  class="action-link action-primary"
                  data-testid="reverse-catalog-start"
                >反向编目</a>
              </td>
            </tr>
          </tbody>
        </table>
      </template>

      <p v-else class="focus-empty">等待数据装载……</p>
    </section>
  </main>
</template>

<style scoped>
.crumbs { margin-bottom: 4px; }
.crumbs a { font-size: 13px; color: var(--b-primary, #006be6); text-decoration: none; }
.crumbs a:hover { text-decoration: underline; }
.filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 14px;
  margin-bottom: 16px;
}
.filter-input {
  flex: 1 1 200px;
  min-width: 160px;
  padding: 7px 12px;
  border: 1px solid var(--b-border, #d4e2f4);
  border-radius: 6px;
  font-size: 13px;
  color: var(--b-neutral-text, #1a1d21);
  background: #fff;
  outline: none;
  transition: border-color 0.15s;
}
.filter-input:focus {
  border-color: var(--b-primary, #006be6);
}
.filter-select {
  flex: 0 0 auto;
  padding: 7px 10px;
  border: 1px solid var(--b-border, #d4e2f4);
  border-radius: 6px;
  font-size: 13px;
  color: var(--b-neutral-text, #1a1d21);
  background: #fff;
  cursor: pointer;
  outline: none;
}
.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  border: 1px solid var(--b-border, #d4e2f4);
  border-radius: 8px;
  overflow: hidden;
}
.data-table thead {
  background: #f5f9fe;
}
.data-table th {
  text-align: left;
  padding: 10px 14px;
  font-size: 13px;
  font-weight: 600;
  color: var(--b-muted, #5c6370);
  border-bottom: 1px solid var(--b-border, #d4e2f4);
  white-space: nowrap;
}
.data-table td {
  padding: 12px 14px;
  color: var(--b-neutral-text, #1a1d21);
  border-bottom: 1px solid var(--b-border-subtle, #e6eef8);
}
.data-table tbody tr:last-child td {
  border-bottom: none;
}
.data-table tbody tr:hover {
  background: #fafcff;
}
.cell-name {
  font-weight: 500;
}
.empty-cell {
  text-align: center;
  color: var(--b-muted, #5c6370);
  padding: 40px 14px !important;
}
.status-tag {
  display: inline-flex;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 500;
}
.status-done {
  background: #e8f5e9;
  color: #2e7d32;
}
.status-pending {
  background: #fff3e0;
  color: #e65100;
}
.status-detail {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: var(--b-muted, #5c6370);
}
.cell-actions {
  display: flex;
  gap: 10px;
}
.action-link {
  color: var(--b-primary, #006be6);
  text-decoration: none;
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
}
.action-link:hover {
  text-decoration: underline;
}
.action-primary {
  font-weight: 600;
}
</style>
