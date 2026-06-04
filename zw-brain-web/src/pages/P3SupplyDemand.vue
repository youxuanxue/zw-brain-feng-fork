<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailPanel from '@/components/DetailPanel.vue';
import DetailActions from '@/components/DetailActions.vue';
import { authFetch } from '@/composables/useAuth';
import { invokeActionStub } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';
import { mapDetailRows } from '@/lib/detailDisplay';
import { formatTodoStatus, todoStatusTone } from '@/lib/statusLabels';
import { apiUrl } from '@/composables/useApiBase';

interface DemandRow {
  id: string;
  title: string;
  demand_phase: string;
  status: string;
  target_resource_hint: string;
  applicant_dept: string;
  channel_class: string;
}

const PHASE_ORDER = [
  'gap_discovered',
  'registered',
  'provider_responded',
  'subscribed',
] as const;

const PHASE_STEPS = PHASE_ORDER.map((key) => ({
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
const detailRef = ref<HTMLElement | null>(null);

function mapDemandRow(row: Record<string, unknown>): DemandRow {
  return {
    id: String(row.id ?? ''),
    title: String(row.title ?? '—'),
    demand_phase: String(row.demand_phase ?? 'gap_discovered'),
    status: String(row.status ?? ''),
    target_resource_hint: String(row.target_resource_hint ?? ''),
    applicant_dept: String(row.applicantDept ?? row.applicant_dept ?? '—'),
    channel_class: String(row.channel_class ?? 'internal'),
  };
}

function sortDemands(rows: DemandRow[]): DemandRow[] {
  return [...rows].sort((a, b) => b.id.localeCompare(a.id));
}

async function loadDemands() {
  loading.value = true;
  try {
    const resp = await authFetch(apiUrl('/api/skills/demand.list'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ role: getProductRole().value }),
    });
    if (!resp.ok) throw new Error('暂时无法加载需求列表，请稍后再试。');
    const payload = (await resp.json()) as { items?: Record<string, unknown>[] };
    items.value = sortDemands((payload.items ?? []).map(mapDemandRow));
  } finally {
    loading.value = false;
  }
}

onMounted(() => { void loadDemands(); });

const selected = computed(() => items.value.find((d) => d.id === selectedId.value) ?? null);

const nextPhase = computed(() => {
  const current = selected.value?.demand_phase ?? 'gap_discovered';
  const idx = PHASE_ORDER.indexOf(current as (typeof PHASE_ORDER)[number]);
  if (idx < 0 || idx >= PHASE_ORDER.length - 1) return null;
  return PHASE_ORDER[idx + 1];
});

const currentPhaseIndex = computed(() => {
  const current = selected.value?.demand_phase ?? '';
  const idx = PHASE_ORDER.indexOf(current as (typeof PHASE_ORDER)[number]);
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
    { label: '当前阶段', value: formatTodoStatus(d.demand_phase) },
    { label: '处理状态', value: formatTodoStatus(d.status) },
    { label: '通道', value: CHANNEL_LABELS[d.channel_class] ?? d.channel_class },
  ]);
});

const headerMeta = computed(() =>
  loading.value ? '正在加载……' : `${items.value.length} 条登记 · 选中后可查看详情并推进阶段`,
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
  if (!title.value.trim()) return;
  const result = await invokeActionStub({
    skillId: 'demand.register',
    payload: {
      title: title.value.trim(),
      target_resource_hint: hint.value.trim() || undefined,
      applicant_dept: '申请部门',
    },
    successTitle: '需求已登记',
    refreshSnapshotAfter: true,
  });
  const data = result.data as Record<string, unknown> | undefined;
  const inner = (data?.result ?? data) as Record<string, unknown> | undefined;
  const newId = String(inner?.id ?? '');
  title.value = '';
  hint.value = '';
  await loadDemands();
  if (newId) await selectDemand(newId);
}

async function advancePhase() {
  if (!selected.value || !nextPhase.value) return;
  await invokeActionStub({
    skillId: 'demand.phase.advance',
    payload: { demand_id: selected.value.id, next_phase: nextPhase.value },
    successTitle: '阶段已推进',
    refreshSnapshotAfter: true,
  });
  const keepId = selected.value.id;
  await loadDemands();
  selectedId.value = keepId;
  await scrollToDetail();
}

function phaseStepClass(index: number): string {
  const current = currentPhaseIndex.value;
  if (current < 0) return 'phase-step';
  if (index < current) return 'phase-step phase-step-done';
  if (index === current) return 'phase-step phase-step-current';
  return 'phase-step';
}
</script>

<template>
  <main class="focus-page">
    <nav class="crumbs"><a href="#/request-flow">← 申请与跟踪</a></nav>
    <section class="panel">
      <PageFocusHeader
        title="找不到数据 · 登记需求"
        :meta="headerMeta"
        :links="[{ label: '资源发现', href: '#/discovery' }]"
      />

      <div class="form-grid">
        <label for="demand-title">需求标题</label>
        <input id="demand-title" v-model="title" placeholder="描述找不到的数据用途" />
        <label for="demand-hint">期望资源提示（可选）</label>
        <input id="demand-hint" v-model="hint" placeholder="关键词或资源类型" />
        <DetailActions>
          <button type="button" class="gov-btn gov-btn-primary" :disabled="!title.trim()" @click="registerDemand">
            登记需求
          </button>
        </DetailActions>
      </div>

      <div ref="detailRef" class="detail-workspace">
        <template v-if="selected">
          <DetailPanel
            title="当前需求"
            :subtitle="`${selected.title} · ${formatTodoStatus(selected.demand_phase)}`"
            :rows="detailRows"
          />

          <div class="phase-track" aria-label="阶段进度">
            <div
              v-for="(step, index) in PHASE_STEPS"
              :key="step.key"
              :class="phaseStepClass(index)"
            >
              <span class="phase-dot">{{ index + 1 }}</span>
              <span class="phase-label">{{ step.label }}</span>
            </div>
          </div>

          <DetailActions v-if="nextPhase">
            <button type="button" class="gov-btn gov-btn-primary" @click="advancePhase">
              推进至「{{ formatTodoStatus(nextPhase) }}」
            </button>
          </DetailActions>
          <p v-else class="phase-complete">该需求已走完本页可见的 4 步路径，无需再推进。</p>
        </template>
        <p v-else-if="items.length" class="detail-hint">在下方列表点击一条需求，查看详情并推进阶段。</p>
      </div>

      <table v-if="items.length" class="focus-table">
        <thead>
          <tr>
            <th>编号</th>
            <th>标题</th>
            <th>期望资源</th>
            <th>阶段</th>
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
            <td><span class="status-pill" :class="todoStatusTone(d.demand_phase)">{{ formatTodoStatus(d.demand_phase) }}</span></td>
            <td>{{ formatTodoStatus(d.status) }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else-if="!loading" class="focus-empty">暂无登记记录，填写上方表单提交第一条需求。</p>
    </section>
  </main>
</template>

<style scoped>
.form-grid { display: grid; gap: 8px; max-width: 560px; margin-bottom: 16px; }
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
