<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DeliveryEntryTabs from '@/components/DeliveryEntryTabs.vue';
import DetailPanel from '@/components/DetailPanel.vue';
import DetailActions from '@/components/DetailActions.vue';
import { authFetch } from '@/composables/useAuth';
import { invokeActionStub } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';
import { mapDetailRows } from '@/lib/detailDisplay';
import { formatTodoStatus, todoStatusTone } from '@/lib/statusLabels';
import { apiUrl } from '@/composables/useApiBase';
import { canPerformAction } from '@/lib/pageAccess';

interface DemandRow {
  id: string;
  title: string;
  response_status: string;
  status: string;
  target_resource_hint: string;
  applicant_dept: string;
  channel_class: string;
  provider_decision: string;
  provider_response_note: string;
  provider_resource_ref: string;
  closed_note: string;
  closed_at: string;
}

const STATUS_ORDER = [
  'pending_response',
  'responded',
  'closed',
] as const;

const STATUS_STEPS = STATUS_ORDER.map((key) => ({
  key,
  label: formatTodoStatus(key),
}));

const CHANNEL_LABELS: Record<string, string> = {
  internal: '平台内',
  national: '国家通道',
};

const items = ref<DemandRow[]>([]);
const title = ref('');
const hint = ref('');
const selectedId = ref('');
const loading = ref(true);
const loadError = ref('');
const detailRef = ref<HTMLElement | null>(null);
const role = getProductRole();
const canRegisterDemand = computed(() => canPerformAction('demand.register', role.value));
const canCloseDemand = computed(() => canPerformAction('demand.close', role.value));

function mapDemandRow(row: Record<string, unknown>): DemandRow {
  return {
    id: String(row.id ?? ''),
    title: String(row.title ?? '—'),
    response_status: String(row.response_status ?? row.status ?? 'pending_response'),
    status: String(row.status ?? ''),
    target_resource_hint: String(row.target_resource_hint ?? ''),
    applicant_dept: String(row.applicantDept ?? row.applicant_dept ?? '—'),
    channel_class: String(row.channel_class ?? 'internal'),
    provider_decision: String(row.provider_decision ?? ''),
    provider_response_note: String(row.provider_response_note ?? ''),
    provider_resource_ref: String(row.provider_resource_ref ?? ''),
    closed_note: String(row.closed_note ?? ''),
    closed_at: String(row.closed_at ?? ''),
  };
}

function sortDemands(rows: DemandRow[]): DemandRow[] {
  return [...rows].sort((a, b) => b.id.localeCompare(a.id));
}

async function loadDemands() {
  loading.value = true;
  loadError.value = '';
  try {
    const resp = await authFetch(apiUrl('/api/skills/demand.list'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ role: getProductRole().value }),
    });
    if (!resp.ok) throw new Error('暂时无法加载需求列表，请稍后再试。');
    const payload = (await resp.json()) as { items?: Record<string, unknown>[] };
    items.value = sortDemands((payload.items ?? []).map(mapDemandRow));
  } catch (e) {
    // 后端故障 / 超时不能伪装成「暂无登记记录」空态：留 error 态 + 重试入口（与 P3ObjectionInbox 同口径）。
    loadError.value = e instanceof Error ? e.message : '暂时无法加载需求列表，请稍后再试。';
  } finally {
    loading.value = false;
  }
}

onMounted(() => { void loadDemands(); });

const selected = computed(() => items.value.find((d) => d.id === selectedId.value) ?? null);

const currentStatusIndex = computed(() => {
  const current = selected.value?.response_status ?? '';
  const idx = STATUS_ORDER.indexOf(current as (typeof STATUS_ORDER)[number]);
  return idx;
});

const detailRows = computed(() => {
  const d = selected.value;
  if (!d) return [];
  return mapDetailRows([
    { label: '需求编号', value: d.id },
    { label: '需求标题', value: d.title },
    { label: '期望资源', value: d.target_resource_hint || '未填写' },
    { label: '申请部门', value: d.applicant_dept },
    { label: '响应状态', value: formatTodoStatus(d.response_status) },
    { label: '通道', value: CHANNEL_LABELS[d.channel_class] ?? d.channel_class },
    { label: '提供方结论', value: d.provider_decision ? formatTodoStatus(d.provider_decision) : '待提供方响应' },
    { label: '处理意见', value: d.provider_response_note || '—' },
    { label: '关联资源', value: d.provider_resource_ref || '—' },
    { label: '关闭说明', value: d.closed_note || '—' },
    { label: '关闭时间', value: d.closed_at || '—' },
  ]);
});

const headerMeta = computed(() =>
  loading.value
    ? '正在加载……'
    : loadError.value
      ? loadError.value
      : `${items.value.length} 条登记 · 选中后可跟踪提供方响应`,
);

async function scrollToDetail() {
  await nextTick();
  detailRef.value?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

async function selectDemand(id: string) {
  selectedId.value = id;
  await scrollToDetail();
}

async function registerDemand() {
  if (!canRegisterDemand.value) return;
  if (!title.value.trim()) return;
  const result = await invokeActionStub({
    skillId: 'demand.register',
    payload: {
      title: title.value.trim(),
      target_resource_hint: hint.value.trim() || undefined,
      // applicant_dept 由后端从会话机构派生（caller_org_code → org_name），前端不再写死固定字面量。
    },
    successTitle: '需求已登记',
    refreshSnapshotAfter: true,
  });
  // 失败（403/422/5xx）：保留用户已填的标题/期望资源，不清空、不伪装成功（invokeActionStub 已弹错误 toast）。
  if (!result.ok) return;
  const data = result.data as Record<string, unknown> | undefined;
  const inner = (data?.result ?? data) as Record<string, unknown> | undefined;
  const newId = String(inner?.id ?? '');
  title.value = '';
  hint.value = '';
  await loadDemands();
  if (newId) await selectDemand(newId);
}

async function closeDemand() {
  const d = selected.value;
  if (!d || d.response_status !== 'responded' || !canCloseDemand.value) return;
  const result = await invokeActionStub({
    skillId: 'demand.close',
    payload: {
      demand_id: d.id,
      close_note: '需求方已确认提供方响应结果。',
    },
    successTitle: '需求已关闭',
    refreshSnapshotAfter: true,
  });
  if (!result.ok) return;
  await loadDemands();
  await selectDemand(d.id);
}

function statusStepClass(index: number): string {
  const current = currentStatusIndex.value;
  if (current < 0) return 'phase-step';
  if (index < current) return 'phase-step phase-step-done';
  if (index === current) return 'phase-step phase-step-current';
  return 'phase-step';
}
</script>

<template>
  <main class="focus-page">
    <section class="panel">
      <PageFocusHeader
        title="领数据"
        :meta="headerMeta"
      />
      <DeliveryEntryTabs active="demands" :demand-count="items.length" />

      <div class="section-head">
        <h2>我的需求</h2>
      </div>

      <div v-if="canRegisterDemand" class="form-grid">
        <label for="demand-title">需求标题</label>
        <input id="demand-title" v-model="title" maxlength="100" placeholder="描述找不到的数据用途" />
        <label for="demand-hint">期望资源提示（可选）</label>
        <input id="demand-hint" v-model="hint" maxlength="80" placeholder="关键词或资源类型" />
        <DetailActions>
          <button type="button" class="gov-btn gov-btn-primary" :disabled="!title.trim()" @click="registerDemand">
            登记需求
          </button>
        </DetailActions>
      </div>

      <div v-if="selected || items.length" ref="detailRef" class="detail-workspace">
        <template v-if="selected">
          <DetailPanel
            title="当前需求"
            :subtitle="`${selected.title} · ${formatTodoStatus(selected.response_status)}`"
            :rows="detailRows"
          />

          <div class="phase-track" aria-label="阶段进度">
            <div
              v-for="(step, index) in STATUS_STEPS"
              :key="step.key"
              :class="statusStepClass(index)"
            >
              <span class="phase-dot">{{ index + 1 }}</span>
              <span class="phase-label">{{ step.label }}</span>
            </div>
          </div>

          <DetailActions v-if="selected.response_status === 'responded' && canCloseDemand">
            <button type="button" class="gov-btn gov-btn-primary" @click="closeDemand">确认完成</button>
          </DetailActions>
          <p v-if="selected.response_status === 'responded' && canCloseDemand" class="phase-complete">
            提供方已响应。确认结果无误后，由需求方关闭这条需求。
          </p>
          <p v-else-if="selected.response_status === 'closed'" class="phase-complete">需求已关闭，供需对接完成。</p>
          <p v-else class="phase-complete">需求提交后由提供方受理并响应，本页展示处理进度。</p>
        </template>
        <p v-else-if="items.length" class="detail-hint">在下方列表点击一条需求，查看详情和响应结果。</p>
      </div>

      <table v-if="items.length" class="focus-table">
        <thead>
          <tr>
            <th>编号</th>
            <th>标题</th>
            <th>期望资源</th>
            <th>状态</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="d in items"
            :key="d.id"
            tabindex="0"
            :class="{ selected: d.id === selectedId }"
            @click="selectDemand(d.id)"
            @keydown.enter.prevent="selectDemand(d.id)"
          >
            <td><code>{{ d.id }}</code></td>
            <td class="title-cell">{{ d.title }}</td>
            <td>{{ d.target_resource_hint || '—' }}</td>
            <td><span class="status-pill" :class="todoStatusTone(d.response_status)">{{ formatTodoStatus(d.response_status) }}</span></td>
          </tr>
        </tbody>
      </table>
      <p v-else-if="loadError" class="focus-empty">
        {{ loadError }}
        <button type="button" class="gov-btn" style="margin-left: 8px" @click="loadDemands">重试</button>
      </p>
      <p v-else-if="!loading" class="focus-empty">
        {{ canRegisterDemand ? '暂无登记记录，填写上方表单提交第一条需求。' : '暂无登记记录。' }}
      </p>
    </section>
  </main>
</template>

<style scoped>
.form-grid { display: grid; gap: 8px; max-width: 560px; margin-bottom: 16px; }
.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 4px 0 12px;
}
.section-head h2 {
  margin: 0;
  font-size: 16px;
  line-height: 1.4;
  color: var(--b-neutral-text, #1a1d21);
}
label { font-size: 13px; color: var(--b-muted, #5c6370); }
input { padding: 8px 10px; border: 1px solid var(--b-border, #d4e2f4); border-radius: 6px; }
.gov-btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid transparent; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.detail-workspace {
  margin: 16px 0;
  padding: 14px 16px;
  border: 1px solid var(--b-border, #d4e2f4);
  border-radius: 10px;
  background: #f8fbff;
}
.detail-hint { margin: 0; color: var(--b-muted, #5c6370); font-size: 13px; }
.phase-track {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  margin: 12px 0;
}
.phase-step {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 999px;
  background: #fff;
  border: 1px solid var(--b-border, #d4e2f4);
  font-size: 12px;
  color: var(--b-muted, #5c6370);
}
.phase-step-current {
  border-color: var(--b-primary, #006be6);
  color: var(--b-primary, #006be6);
  background: #eef5ff;
  font-weight: 600;
}
.phase-step-done {
  border-color: #8bc48a;
  color: #2d6a2d;
  background: #f3fbf3;
}
.phase-dot {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #9aa3b2;
  color: #fff;
  font-size: 10px;
  font-weight: 700;
}
.phase-step-current .phase-dot { background: var(--b-primary, #006be6); }
.phase-step-done .phase-dot { background: #3d8b40; }
.phase-complete { margin: 8px 0 0; font-size: 13px; color: #2d6a2d; }
.focus-table tbody tr {
  cursor: pointer;
}
.focus-table tbody tr.selected {
  background: #eef5ff;
  box-shadow: inset 3px 0 0 var(--b-primary, #006be6);
}
.title-cell { max-width: 240px; }
.focus-empty { color: var(--b-muted, #5c6370); font-size: 13px; }
</style>
