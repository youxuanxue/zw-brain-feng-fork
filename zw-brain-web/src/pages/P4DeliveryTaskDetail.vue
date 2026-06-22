<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailPanel from '@/components/DetailPanel.vue';
import DetailActions from '@/components/DetailActions.vue';
import PhaseTrack from '@/components/PhaseTrack.vue';
import { lookupDeliveryTask, useSnapshot } from '@/composables/useSnapshot';
import { invokeActionStub } from '@/composables/useActionStub';
import { downloadDeliveryFile } from '@/composables/useDeliveryDownload';
import { mapDetailRows } from '@/lib/detailDisplay';
import { formatTodoStatus } from '@/lib/statusLabels';
import { displayRecordName, formatChannel, shortId } from '@/lib/userLanguage';
import { getProductRole } from '@/composables/useProductRole';
import { canPerformAction } from '@/lib/pageAccess';

const route = useRoute();
const id = computed(() => String(route.params.id ?? ''));
const taskRef = lookupDeliveryTask(id.value);
const { source } = useSnapshot();
const role = getProductRole();

// 失败态恢复（delivery.trigger_recovery，部门管理员）：交付任务投递失败时此前**无任何 UI 入口**——
// 后端 capability/policy/契约俱全却成孤儿门。归位到任务详情失败态：状态=failed 且有权时渲染「触发恢复」，
// 无权岗位不可见（GatedAction 同口径 canPerformAction 自门控）。恢复把 failed→warning（等审计链修复后重核）。
const isFailed = computed(() => String((taskRef.value as Record<string, unknown> | null)?.status ?? '') === 'failed');
const canRecover = computed(() => isFailed.value && canPerformAction('delivery.trigger_recovery', role.value));

// 三角色脊柱：交付员也看见整单进度（后端 enrich_delivery_tasks_snapshot 已挂同一条 timeline）。
const timeline = computed(() => {
  const arr = (taskRef.value as Record<string, unknown> | null)?.statusTimeline;
  return Array.isArray(arr) ? (arr as Array<{ stage: string; status: string; label: string; holder?: string }>) : [];
});

// 交付说明（后端 task.note）：让交付方看见「在等谁、补什么」——脊柱旁直出，缺则不渲染（诚实空）。
const note = computed(() => String((taskRef.value as Record<string, unknown> | null)?.note ?? '').trim());

// 按资源类型分流（0611 业务口径确认单 §B，2026-06-12 方案 B 终裁）：
// API=查看授权、文件=下载、库表=交换任务语系（标题「交换任务」+ 按钮「核对交换结果」）；
// 类型推不出时回落「查看授权」（与列表页同一回落口径）。
const resourceKind = computed(() => String((taskRef.value as Record<string, unknown> | null)?.resourceKind ?? ''));
const isTable = computed(() => resourceKind.value === 'table');
// R12：标题用任务真实名（task.name；displayRecordName 优先真实名，名缺失/为裸 id 时降级为
// 「未命名{交换/交付任务}（编码 …末6位）」），不再硬编码「交付任务/交换任务 <hex id>」直出 id。
const taskCategory = computed(() => (isTable.value ? '交换任务' : '交付任务'));
const pageTitle = computed(() =>
  displayRecordName((taskRef.value as Record<string, unknown> | null)?.name, id.value, taskCategory.value),
);

const rows = computed(() => {
  const t = taskRef.value;
  if (!t) return [];
  const repo = (t.repository as Record<string, unknown> | undefined) ?? {};
  const rawReqId = String(t.requestId ?? repo.application_code ?? '');
  return mapDetailRows([
    // R12：编号类字段缩成末 6 位短码展示（避免裸长 id 撑列）；'状态' 经 formatTodoStatus 中文化
    // （DetailPanel 亦按「状态」标签自动归一，此处显式同口径）；'渠道' 经 formatChannel 译为业务用语。
    { label: '任务编号', value: shortId(id.value) },
    { label: '名称', value: String(t.name ?? '—') },
    { label: '状态', value: formatTodoStatus(String(t.status ?? '')) },
    { label: '渠道', value: formatChannel(t.channel ?? repo.channel) },
    { label: '关联申请', value: rawReqId ? shortId(rawReqId) : '—' },
    { label: '更新时间', value: String(t.updatedAt ?? '—') },
  ]);
});

const headerMeta = computed(() => {
  if (source.value !== 'live') return '正在加载……';
  if (!taskRef.value) return `未找到该${isTable.value ? '交换' : '交付'}任务`;
  return formatTodoStatus(String(taskRef.value.status ?? ''));
});

// 「提异议」入口默认带 type=delivery+id；用户在 P3ObjectionNew 仍可改维度
const objectionLink = computed(() => {
  const tid = encodeURIComponent(id.value);
  return `#/request-flow/objection/new?type=delivery&id=${tid}`;
});

async function openCredential() {
  const reqId = String(taskRef.value?.requestId ?? '');
  if (reqId) window.location.hash = `#/delivery-exchange/credential/${reqId}`;
}

async function reconcile() {
  await invokeActionStub({
    skillId: 'delivery.reconcile_receipt',
    payload: { task_id: id.value },
    successTitle: '已发起交换结果核对',
  });
}

async function triggerRecovery() {
  await invokeActionStub({
    skillId: 'delivery.trigger_recovery',
    payload: { task_id: id.value },
    successTitle: '已触发恢复流程',
  });
}

// 文件资源受控下载（与列表页 F4 同一语义）：语义与文案单源在 useDeliveryDownload。
async function downloadFile() {
  const t = taskRef.value as Record<string, unknown> | null;
  await downloadDeliveryFile(id.value, String(t?.name ?? ''));
}
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/delivery-exchange">← 交付任务列表</a></nav>
    <section class="panel">
      <PageFocusHeader
        :title="pageTitle"
        :meta="headerMeta"
        :links="[{ label: '提异议', href: objectionLink }]"
      >
        <p v-if="id" class="record-code">编号 <span :title="id">{{ shortId(id) }}</span></p>
      </PageFocusHeader>
      <PhaseTrack :steps="timeline" aria-label="交付进度" />
      <p v-if="note" class="delivery-note">{{ note }}</p>
      <DetailPanel v-if="rows.length" :title="isTable ? '交换任务详情' : '任务详情'" :rows="rows" />
      <p v-else-if="source === 'live'" class="focus-empty">{{ isTable ? '未找到该交换任务。' : '未找到该交付任务。' }}</p>
      <p v-else class="focus-empty">等待数据装载……</p>
      <DetailActions v-if="taskRef">
        <!-- 失败态恢复优先（写关键，部门管理员）：归位的孤儿 CTA，无权/非失败态不渲染。 -->
        <button v-if="canRecover" type="button" class="gov-btn gov-btn-primary" @click="triggerRecovery">
          触发恢复
        </button>
        <button v-if="resourceKind === 'file'" type="button" class="gov-btn gov-btn-primary" @click="downloadFile">
          下载
        </button>
        <button v-else-if="isTable" type="button" class="gov-btn gov-btn-primary" @click="reconcile">
          核对交换结果
        </button>
        <button v-else type="button" class="gov-btn gov-btn-secondary" @click="openCredential">查看授权</button>
      </DetailActions>
    </section>
  </main>
</template>

<style scoped>
.gov-btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid transparent; margin-right: 8px; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-secondary { background: #fff; border-color: var(--b-border, #d4e2f4); }
.delivery-note {
  margin: 12px 0 4px;
  padding: 10px 12px;
  border-radius: 8px;
  background: #f2f7ff;
  border: 1px solid var(--b-border, #d4e2f4);
  border-left: 3px solid var(--b-primary, #006be6);
  font-size: 13px;
  line-height: 1.7;
  color: var(--b-text, #1a1a1a);
}
.record-code { margin: 0; font-size: 12px; color: var(--b-muted, #5c6370); }
.record-code span { font-family: var(--b-mono, ui-monospace, SFMono-Regular, Menlo, monospace); cursor: help; }
</style>
