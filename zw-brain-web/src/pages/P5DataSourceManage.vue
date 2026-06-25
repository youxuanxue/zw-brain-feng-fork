<script setup lang="ts">
import { computed, ref } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import ReferencePicker from '@/components/ReferencePicker.vue';
import { useProvider, useSnapshot } from '@/composables/useSnapshot';
import { invokeActionStub, pushToast } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';
import {
  datasourceEndpointsFromProvider,
  partitionLabel,
  connectivityLabel,
  connectivityTagClass,
  dbTypeLabel,
  type DatasourceEndpointRow,
} from '@/lib/datasourceEndpoints';

const { source } = useSnapshot();
const provider = useProvider();
const role = getProductRole();

const activePartition = ref<'front' | 'standard' | 'service'>('front');
const searchQuery = ref('');
const statusFilter = ref('');
const showForm = ref(false);
const editingId = ref('');
const busy = ref(false);

const form = ref({
  display_name: '',
  db_name: '',
  db_type: 'mysql',
  host_display: '',
  port: '',
  org_code: '',
  org_name: '',
  contact_name: '',
  contact_phone: '',
  data_partition: 'front' as 'front' | 'standard' | 'service',
  remark: '',
});

const partitions = [
  { key: 'front' as const, label: '前置库' },
  { key: 'standard' as const, label: '标准库' },
  { key: 'service' as const, label: '服务库' },
];

const allRows = computed(() => datasourceEndpointsFromProvider(provider.value as Record<string, unknown>));

const filteredRows = computed(() => {
  let list = allRows.value.filter((r) => r.data_partition === activePartition.value);
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.trim().toLowerCase();
    list = list.filter(
      (r) => r.display_name.toLowerCase().includes(q)
        || r.db_name.toLowerCase().includes(q)
        || (r.org_name ?? '').toLowerCase().includes(q),
    );
  }
  if (statusFilter.value) {
    list = list.filter((r) => r.connectivity_status === statusFilter.value);
  }
  return list;
});

const partitionCounts = computed(() => {
  const counts: Record<'front' | 'standard' | 'service', number> = {
    front: 0,
    standard: 0,
    service: 0,
  };
  for (const row of allRows.value) {
    if (row.data_partition in counts) counts[row.data_partition] += 1;
  }
  return counts;
});

const headerMeta = computed(() => {
  if (source.value !== 'live') return '正在加载……';
  return filteredRows.value.length
    ? `${partitionLabel(activePartition.value)} ${filteredRows.value.length} 个数据源`
    : `${partitionLabel(activePartition.value)}暂无数据源，可点「登记数据源」`;
});

function partitionButtonLabel(key: 'front' | 'standard' | 'service', label: string): string {
  const n = partitionCounts.value[key];
  return n > 0 ? `${label}（${n}）` : label;
}

function resetForm() {
  editingId.value = '';
  form.value = {
    display_name: '',
    db_name: '',
    db_type: 'mysql',
    host_display: '',
	    port: '',
	    org_code: '',
	    org_name: '',
    contact_name: '',
    contact_phone: '',
    data_partition: activePartition.value,
    remark: '',
  };
}

function openCreate() {
  resetForm();
  form.value.data_partition = activePartition.value;
  showForm.value = true;
}

function openEdit(row: DatasourceEndpointRow) {
  editingId.value = row.endpoint_id;
  form.value = {
    display_name: row.display_name,
    db_name: row.db_name,
    db_type: row.db_type,
	    host_display: String(row.host ?? ''),
	    port: row.port != null ? String(row.port) : '',
	    org_code: row.org_code ?? '',
	    org_name: row.org_name ?? '',
    contact_name: row.contact_name ?? '',
    contact_phone: row.contact_phone ?? '',
    data_partition: row.data_partition,
    remark: row.remark ?? '',
  };
  showForm.value = true;
}

async function testRow(row: DatasourceEndpointRow) {
  if (!row.endpoint_id) {
    pushToast({ kind: 'info', title: '请先保存后再检查连通性' });
    return;
  }
  const res = await invokeActionStub({
    skillId: 'datasource.connectivity.test',
    payload: { endpoint_id: row.endpoint_id },
    role: role.value,
    suppressSuccessToast: true,
    refreshSnapshotAfter: true,
  });
  const data = res.data as Record<string, unknown> | undefined;
  const status = String(data?.connectivity_status ?? data?.status ?? row.connectivity_status);
  pushToast({
    kind: status === 'connected' || status === 'ok' ? 'ok' : 'warn',
    title: connectivityLabel(status),
    detail: String(data?.error_summary ?? '结果来自最近一次同步记录，非实时探测'),
  });
}

async function saveEndpoint() {
  if (!form.value.display_name.trim() || !form.value.db_name.trim()) {
    pushToast({ kind: 'info', title: '请填写显示名称与库实例名' });
    return;
  }
  busy.value = true;
  try {
    const res = await invokeActionStub({
      skillId: 'datasource.endpoint.upsert',
      payload: {
        endpoint_id: editingId.value || undefined,
        display_name: form.value.display_name.trim(),
        db_name: form.value.db_name.trim(),
        db_type: form.value.db_type,
        host_display: form.value.host_display.trim() || undefined,
        host_ref: form.value.host_display.trim() ? `host:${form.value.host_display.trim()}:${form.value.port || 0}` : undefined,
        port: form.value.port ? Number(form.value.port) : undefined,
	        org_code: form.value.org_code.trim() || undefined,
        contact_name: form.value.contact_name.trim() || undefined,
        contact_phone: form.value.contact_phone.trim() || undefined,
        data_partition: form.value.data_partition,
        remark: form.value.remark.trim() || undefined,
        connectivity_status: 'unknown',
      },
      successTitle: editingId.value ? '数据源已更新' : '数据源已登记',
      role: role.value,
      refreshSnapshotAfter: true,
    });
    if (res.ok) {
      showForm.value = false;
      resetForm();
    }
  } finally {
    busy.value = false;
  }
}

async function deleteRow(row: DatasourceEndpointRow) {
  if (!window.confirm(`确认删除「${row.display_name}」？\n删除后反向编目与挂接将无法再选该数据源。`)) return;
  busy.value = true;
  try {
    await invokeActionStub({
      skillId: 'datasource.endpoint.delete',
      payload: { endpoint_id: row.endpoint_id },
      successTitle: '数据源已删除',
      role: role.value,
      refreshSnapshotAfter: true,
    });
  } finally {
    busy.value = false;
  }
}

function onOrgPicked(opt: { code: string; name: string }) {
  form.value.org_code = opt.code;
  form.value.org_name = opt.name;
}

function onOrgCleared() {
  form.value.org_code = '';
  form.value.org_name = '';
}
</script>

<template>
  <main class="focus-page">
    <nav class="crumbs"><a href="#/provider">← 提供方管理</a></nav>
    <section class="panel">
      <PageFocusHeader
        title="数据源管理"
        :meta="headerMeta"
        :links="[
          { label: '反向编目', href: '#/provider/wizard/reverse-catalog' },
          { label: '资源挂接', href: '#/provider/wizard/hookup-submit' },
        ]"
      />

      <template v-if="source === 'live'">
        <div class="layout">
          <aside class="partition-pane" aria-label="数据分区">
            <button
              v-for="p in partitions"
              :key="p.key"
              type="button"
              class="partition-btn"
              :class="{ active: activePartition === p.key }"
              @click="activePartition = p.key"
            >
              {{ partitionButtonLabel(p.key, p.label) }}
            </button>
          </aside>

          <div class="main-pane">
            <div class="toolbar">
              <input v-model="searchQuery" type="search" class="filter-input" placeholder="名称 / 库实例 / 部门" />
              <select v-model="statusFilter" class="filter-select">
                <option value="">全部连通状态</option>
                <option value="connected">连通</option>
                <option value="disconnected">未连通</option>
                <option value="unknown">未探测</option>
              </select>
              <button type="button" class="btn-primary" data-testid="datasource-add" @click="openCreate">登记数据源</button>
            </div>

            <table class="data-table" data-testid="datasource-table">
              <thead>
                <tr>
                  <th>显示名称</th>
                  <th>库实例名</th>
                  <th>所属部门</th>
                  <th>类型</th>
                  <th>服务器地址</th>
                  <th>端口</th>
                  <th>联系人</th>
                  <th>连通性</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="!filteredRows.length">
                  <td colspan="9" class="empty-cell">
                    暂无数据源。可点「登记数据源」，或联系管理员从旧平台同步。
                  </td>
                </tr>
                <tr v-for="row in filteredRows" :key="row.endpoint_id">
                  <td>{{ row.display_name }}</td>
                  <td class="mono">{{ row.db_name }}</td>
                  <td>{{ row.org_name || '—' }}</td>
                  <td>{{ dbTypeLabel(row.db_type) }}</td>
                  <td>{{ row.host || '—' }}</td>
                  <td>{{ row.port ?? '—' }}</td>
                  <td>{{ row.contact_name || '—' }}</td>
                  <td>
                    <span :class="['status-tag', connectivityTagClass(row.connectivity_status)]">
                      {{ connectivityLabel(row.connectivity_status) }}
                    </span>
                  </td>
                  <td class="cell-actions">
                    <button type="button" class="link-btn" @click="openEdit(row)">编辑</button>
                    <button type="button" class="link-btn" @click="testRow(row)">检查连通</button>
                    <button type="button" class="link-btn danger" @click="deleteRow(row)">删除</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div v-if="showForm" class="modal-backdrop" @click.self="showForm = false">
          <form class="modal" @submit.prevent="saveEndpoint">
            <h2>{{ editingId ? '编辑数据源' : '登记数据源' }}</h2>
            <p v-if="!editingId" class="modal-hint">归属分区：{{ partitionLabel(activePartition) }}（与左侧选中分区一致）</p>
            <label>显示名称<input v-model="form.display_name" required placeholder="例如：省公安厅前置库" /></label>
            <label>库实例名<input v-model="form.db_name" required placeholder="例如：test_gat_qzk" /></label>
            <label>所属部门
              <ReferencePicker
                v-model="form.org_code"
                mode="organ"
                :display-name="form.org_name"
                placeholder="选择所属部门"
                testid="datasource-org-picker"
                @picked="onOrgPicked"
                @cleared="onOrgCleared"
              />
            </label>
            <label>数据库类型
              <select v-model="form.db_type">
                <option value="mysql">MySQL</option>
              </select>
            </label>
            <label>服务器地址<input v-model="form.host_display" placeholder="例如：10.0.0.1" /></label>
            <label>端口<input v-model="form.port" inputmode="numeric" placeholder="3306" /></label>
            <label>联系人<input v-model="form.contact_name" /></label>
            <label>联系电话<input v-model="form.contact_phone" /></label>
            <label v-if="editingId">数据分区
              <select v-model="form.data_partition">
                <option value="front">前置库</option>
                <option value="standard">标准库</option>
                <option value="service">服务库</option>
              </select>
            </label>
            <label>备注<textarea v-model="form.remark" rows="2" /></label>
            <div class="modal-actions">
              <button type="button" class="btn-secondary" @click="showForm = false">取消</button>
              <button
                v-if="editingId"
                type="button"
                class="btn-secondary"
                @click="testRow({ endpoint_id: editingId, connectivity_status: 'unknown', connection_ref: '', display_name: form.display_name, db_name: form.db_name, db_type: form.db_type, data_partition: form.data_partition } as DatasourceEndpointRow)"
              >
                检查连通
              </button>
              <button type="submit" class="btn-primary" :disabled="busy">确定</button>
            </div>
          </form>
        </div>
      </template>
      <p v-else class="focus-empty">等待数据装载……</p>
    </section>
  </main>
</template>

<style scoped>
.crumbs { margin-bottom: 4px; }
.crumbs a { font-size: 13px; color: var(--b-primary, #006be6); text-decoration: none; }
.layout { display: grid; grid-template-columns: 140px 1fr; gap: 16px; margin-top: 14px; }
.partition-pane { display: flex; flex-direction: column; gap: 6px; }
.partition-btn {
  text-align: left; padding: 10px 12px; border: 1px solid var(--b-border, #d4e2f4);
  border-radius: 8px; background: #fff; cursor: pointer; font-size: 13px;
}
.partition-btn.active { border-color: var(--b-primary, #006be6); background: #f0f7ff; font-weight: 600; }
.toolbar { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 12px; }
.filter-input { flex: 1 1 180px; padding: 7px 12px; border: 1px solid var(--b-border, #d4e2f4); border-radius: 6px; }
.filter-select { padding: 7px 10px; border: 1px solid var(--b-border, #d4e2f4); border-radius: 6px; }
.btn-primary, .btn-secondary { padding: 7px 14px; border-radius: 6px; border: none; cursor: pointer; font-size: 13px; }
.btn-primary { background: #2e7d32; color: #fff; }
.btn-secondary { background: #eef3fb; color: #1a1d21; }
.data-table { width: 100%; border-collapse: collapse; font-size: 13px; border: 1px solid var(--b-border, #d4e2f4); border-radius: 8px; overflow: hidden; }
.data-table thead { background: #f5f9fe; }
.data-table th, .data-table td { padding: 10px 12px; border-bottom: 1px solid var(--b-border-subtle, #e6eef8); text-align: left; }
.empty-cell { text-align: center; color: var(--b-muted, #5c6370); padding: 32px !important; }
.mono { font-family: ui-monospace, monospace; font-size: 12px; }
.status-tag { padding: 2px 8px; border-radius: 999px; font-size: 12px; }
.status-tag.ok { background: #e8f5e9; color: #2e7d32; }
.status-tag.warn { background: #fff8e1; color: #8d6e00; }
.status-tag.bad { background: #ffebee; color: #c62828; }
.modal-hint { margin: 0; font-size: 12px; color: var(--b-muted, #5c6370); }
.cell-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.link-btn { background: none; border: none; color: var(--b-primary, #006be6); cursor: pointer; padding: 0; font-size: 13px; }
.link-btn.danger { color: #c62828; }
.modal-backdrop { position: fixed; inset: 0; background: rgba(0,0,0,.35); display: flex; align-items: center; justify-content: center; z-index: 40; }
.modal { background: #fff; border-radius: 10px; padding: 20px; width: min(520px, 92vw); display: grid; gap: 10px; }
.modal label { display: grid; gap: 4px; font-size: 13px; }
.modal input, .modal select, .modal textarea { padding: 7px 10px; border: 1px solid var(--b-border, #d4e2f4); border-radius: 6px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }
</style>
