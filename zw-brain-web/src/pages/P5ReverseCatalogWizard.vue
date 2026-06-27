<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import { shellNavLabelByKey } from '@/config/productShellNav';
import DetailActions from '@/components/DetailActions.vue';
import { useProvider, useSnapshot } from '@/composables/useSnapshot';
import { invokeActionStub, pushToast } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';
import { canPerformAction, isRouteAllowedForRole } from '@/lib/pageAccess';
import { mintResourceCode } from '@/lib/providerActionPayload';
import {
  datasourceEndpointsFromProvider,
  endpointsForOrigin,
  partitionLabel,
} from '@/lib/datasourceEndpoints';
import {
  buildReverseDraftCreatePayload,
  parseFieldSuggestions,
  parseTitleSuggestion,
} from '@/lib/reverseDraftPayload';

type Step = 1 | 2 | 3;
type ResourceOrigin = 'front' | 'landed';

interface TableRow {
  table_meta_id: string;
  table_name: string;
  table_comment: string;
  schema_ref: string;
}

interface ColumnRow {
  column_name: string;
  comment: string;
  data_type: string;
}

const providerShellTitle = shellNavLabelByKey('provider');
const step = ref<Step>(1);
const resourceOrigin = ref<ResourceOrigin>('front');
const selectedEndpointId = ref('');
const tableSearch = ref('');
const selectedTable = ref<TableRow | null>(null);
const columns = ref<ColumnRow[]>([]);
const catalogTitle = ref('');
const catalogCode = ref(mintResourceCode('reverse'));
const busy = ref(false);

const { source } = useSnapshot();
const provider = useProvider();
const role = getProductRole();

const canCreateDraft = computed(() => canPerformAction('catalog.entry.reverse_draft.create', role.value));

const endpoints = computed(() =>
  endpointsForOrigin(
    datasourceEndpointsFromProvider(provider.value as Record<string, unknown>),
    resourceOrigin.value,
  ),
);

const selectedEndpoint = computed(() =>
  endpoints.value.find((e) => e.endpoint_id === selectedEndpointId.value) ?? null,
);

const tables = ref<TableRow[]>([]);
const tablesLoading = ref(false);
const columnsLoading = ref(false);

async function loadTables() {
  if (!selectedEndpoint.value) {
    tables.value = [];
    return;
  }
  tablesLoading.value = true;
  try {
    const res = await invokeActionStub({
      skillId: 'datasource.table.list',
      payload: {
        endpoint_id: selectedEndpoint.value.endpoint_id,
        metadata_database_id: selectedEndpoint.value.metadata_database_id ?? selectedEndpoint.value.endpoint_id,
        search: tableSearch.value.trim() || undefined,
      },
      role: role.value,
      suppressSuccessToast: true,
      refreshSnapshotAfter: false,
    });
    const data = res.data as { items?: TableRow[] } | undefined;
    tables.value = Array.isArray(data?.items) ? data.items : [];
  } finally {
    tablesLoading.value = false;
  }
}

watch(resourceOrigin, () => {
  selectedEndpointId.value = '';
  selectedTable.value = null;
  columns.value = [];
  tables.value = [];
  step.value = 1;
});

watch(selectedEndpointId, () => {
  selectedTable.value = null;
  columns.value = [];
  if (selectedEndpointId.value) void loadTables();
});

watch(tableSearch, () => {
  if (selectedEndpointId.value) void loadTables();
});

async function loadColumns(table: TableRow) {
  selectedTable.value = table;
  columnsLoading.value = true;
  columns.value = [];
  try {
    const res = await invokeActionStub({
      skillId: 'datasource.table.columns',
      payload: { table_meta_id: table.table_meta_id, schema_ref: table.schema_ref },
      role: role.value,
      suppressSuccessToast: true,
      refreshSnapshotAfter: false,
    });
    const data = res.data as { items?: ColumnRow[] } | undefined;
    columns.value = Array.isArray(data?.items) ? data.items : [];
    catalogTitle.value = table.table_comment || table.table_name;
    const suggest = await invokeActionStub({
      skillId: 'catalog.entry.reverse_draft.suggest',
      payload: { schema_ref: table.schema_ref, table_name: table.table_name },
      role: role.value,
      suppressSuccessToast: true,
      refreshSnapshotAfter: false,
    });
    const sdata = suggest.data as Record<string, unknown> | undefined;
    const title = parseTitleSuggestion(sdata ?? {});
    if (title) catalogTitle.value = title;
    const fields = parseFieldSuggestions(sdata ?? {});
    if (fields.length && !columns.value.length) {
      columns.value = fields.map((f) => ({
        column_name: f.field_en,
        comment: f.field_cn,
        data_type: f.data_type,
      }));
    }
  } finally {
    columnsLoading.value = false;
  }
}

function goStep(next: Step) {
  step.value = next;
}

async function createReverseDraft() {
  if (!canCreateDraft.value) {
    pushToast({ kind: 'info', title: '暂无创建权限' });
    return;
  }
  if (!selectedTable.value) {
    pushToast({ kind: 'info', title: '请先选择库表' });
    return;
  }
  busy.value = true;
  try {
    const decisions = columns.value.map((col) => ({
      field_en: col.column_name,
      field_cn: col.comment || col.column_name,
      sensitive_level: '1',
      source: 'schema',
      selected: Boolean(col.column_name.trim()),
    }));
    const payload = buildReverseDraftCreatePayload(
      {
        id: catalogCode.value,
        name: catalogTitle.value.trim() || selectedTable.value.table_name,
        catalog_code: catalogCode.value,
        schema_ref: selectedTable.value.schema_ref,
      },
      decisions,
    );
    const res = await invokeActionStub({
      skillId: 'catalog.entry.reverse_draft.create',
      payload,
      successTitle: '反向编目草稿已创建',
      role: role.value,
      refreshSnapshotAfter: true,
    });
    if (res.ok) {
      const canReview = isRouteAllowedForRole('/provider/inbox/field-decision', role.value);
      pushToast({
        kind: 'ok',
        title: '反向编目草稿已创建',
        detail: canReview ? undefined : '已保存，请通知部门管理员审核',
      });
      window.location.hash = canReview
        ? `#/provider/inbox/field-decision/${encodeURIComponent(catalogCode.value)}`
        : '#/provider';
    }
  } finally {
    busy.value = false;
  }
}

const headerMeta = computed(() => {
  if (source.value !== 'live') return '正在加载……';
  return '已有物理表时，从数据源选表，一键生成目录与信息项';
});
</script>

<template>
  <main class="focus-page">
    <nav class="crumbs"><a href="#/provider">← {{ providerShellTitle }}</a></nav>
    <section class="panel">
      <PageFocusHeader
        title="反向编目"
        :meta="headerMeta"
        :links="[
          { label: '数据源管理', href: '#/provider/datasources' },
          { label: '反向编目审核', href: '#/provider/inbox/field-decision' },
        ]"
      />

      <ol class="steps" aria-label="编目步骤">
        <li :class="{ active: step === 1, done: step > 1 }">1. 选择数据源</li>
        <li :class="{ active: step === 2, done: step > 2 }">2. 选择库表</li>
        <li :class="{ active: step === 3 }">3. 确认并创建草稿</li>
      </ol>

      <template v-if="source === 'live'">
        <section v-if="step === 1" class="step-panel">
          <fieldset class="origin-group">
            <legend>资源来源</legend>
            <label><input v-model="resourceOrigin" type="radio" value="front" /> 前置资源</label>
            <label><input v-model="resourceOrigin" type="radio" value="landed" /> 已落地资源（标准库 / 服务库）</label>
          </fieldset>
          <label class="field">
            数据源
            <select v-model="selectedEndpointId" data-testid="reverse-datasource-select">
              <option value="">请选择数据源</option>
              <option v-for="ep in endpoints" :key="ep.endpoint_id" :value="ep.endpoint_id">
                {{ ep.display_name }}（{{ partitionLabel(ep.data_partition) }}）
              </option>
            </select>
          </label>
          <p v-if="!endpoints.length" class="hint">
            还没有可用数据源。请先到
            <a href="#/provider/datasources">数据源管理</a>
            登记，或联系管理员同步旧平台连接。
          </p>
          <p v-else class="hint">还没有物理表、只想先建目录？请走
            <a href="#/provider/wizard/inline-catalog">在线编制目录</a>。
          </p>
          <DetailActions>
            <button type="button" class="btn-primary" :disabled="!selectedEndpointId" @click="goStep(2)">下一步</button>
          </DetailActions>
        </section>

        <section v-else-if="step === 2" class="step-panel">
          <p class="hint">数据源：{{ selectedEndpoint?.display_name }}（{{ selectedEndpoint?.db_name }}）</p>
          <input v-model="tableSearch" type="search" class="filter-input" placeholder="库表名称" />
          <table class="data-table">
            <thead>
              <tr><th>表名称</th><th>表注释</th><th>操作</th></tr>
            </thead>
            <tbody>
              <tr v-if="tablesLoading"><td colspan="3" class="empty">正在加载库表……</td></tr>
              <tr v-else-if="!tables.length">
                <td colspan="3" class="empty">
                  该数据源下还没有可用表。请确认已完成库表采集，或改选其他数据源。
                </td>
              </tr>
              <tr v-for="t in tables" :key="t.table_meta_id">
                <td>{{ t.table_name }}</td>
                <td>{{ t.table_comment || '—' }}</td>
                <td><button type="button" class="link-btn" @click="loadColumns(t); goStep(3)">选择</button></td>
              </tr>
            </tbody>
          </table>
          <DetailActions>
            <button type="button" class="btn-secondary" @click="goStep(1)">上一步</button>
          </DetailActions>
        </section>

        <section v-else class="step-panel">
          <label class="field">目录名称<input v-model="catalogTitle" placeholder="例如：学生基本信息" /></label>
          <p class="hint">来源表：{{ selectedTable?.table_name }} · 信息项 {{ columns.length }} 个</p>
          <table class="data-table">
            <thead><tr><th>字段名</th><th>中文释义</th><th>类型</th></tr></thead>
            <tbody>
              <tr v-if="columnsLoading"><td colspan="3" class="empty">正在加载字段……</td></tr>
              <tr v-else-if="!columns.length"><td colspan="3" class="empty">未读取到字段，请返回上一步重选表</td></tr>
              <tr v-for="col in columns" :key="col.column_name">
                <td>{{ col.column_name }}</td>
                <td>{{ col.comment || '—' }}</td>
                <td>{{ col.data_type || '—' }}</td>
              </tr>
            </tbody>
          </table>
          <DetailActions>
            <button type="button" class="btn-secondary" @click="goStep(2)">上一步</button>
            <button
              type="button"
              class="btn-primary"
              data-testid="reverse-catalog-create"
              :disabled="busy || columnsLoading || !canCreateDraft || !catalogTitle.trim() || !columns.length"
              @click="createReverseDraft"
            >
              创建反向编目草稿
            </button>
          </DetailActions>
        </section>
      </template>
      <p v-else class="focus-empty">等待数据装载……</p>
    </section>
  </main>
</template>

<style scoped>
.crumbs { margin-bottom: 4px; }
.crumbs a { font-size: 13px; color: var(--b-primary, #006be6); text-decoration: none; }
.steps { display: flex; gap: 16px; list-style: none; padding: 0; margin: 14px 0; font-size: 13px; color: var(--b-muted, #5c6370); }
.steps li.active { color: var(--b-primary, #006be6); font-weight: 600; }
.steps li.done { color: #2e7d32; }
.step-panel { display: grid; gap: 12px; }
.origin-group { border: none; display: flex; gap: 16px; padding: 0; }
.field { display: grid; gap: 6px; font-size: 13px; }
.field input, .field select, .filter-input { padding: 8px 10px; border: 1px solid var(--b-border, #d4e2f4); border-radius: 6px; }
.hint { font-size: 13px; color: var(--b-muted, #5c6370); }
.data-table { width: 100%; border-collapse: collapse; font-size: 13px; border: 1px solid var(--b-border, #d4e2f4); }
.data-table th, .data-table td { padding: 10px 12px; border-bottom: 1px solid var(--b-border-subtle, #e6eef8); text-align: left; }
.empty { text-align: center; color: var(--b-muted, #5c6370); }
.link-btn, .btn-primary, .btn-secondary { font-size: 13px; cursor: pointer; border-radius: 6px; padding: 7px 14px; border: none; }
.btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.btn-secondary { background: #eef3fb; }
.link-btn { background: none; color: var(--b-primary, #006be6); padding: 0; }
</style>
