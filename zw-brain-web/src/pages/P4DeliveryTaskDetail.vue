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

const route = useRoute();
const id = computed(() => String(route.params.id ?? ''));
const taskRef = lookupDeliveryTask(id.value);
const { source } = useSnapshot();

// 三角色脊柱：交付员也看见整单进度（后端 enrich_delivery_tasks_snapshot 已挂同一条 timeline）。
const timeline = computed(() => {
  const arr = (taskRef.value as Record<string, unknown> | null)?.statusTimeline;
  return Array.isArray(arr) ? (arr as Array<{ stage: string; status: string; label: string; holder?: string }>) : [];
});

// 按资源类型分流（0611 业务口径确认单 §B，2026-06-12 方案 B 终裁）：
// API=查看授权、文件=下载、库表=交换任务语系（标题「交换任务」+ 按钮「核对交换结果」）；
// 类型推不出时回落「查看授权」（与列表页同一回落口径）。
const resourceKind = computed(() => String((taskRef.value as Record<string, unknown> | null)?.resourceKind ?? ''));
const isTable = computed(() => resourceKind.value === 'table');
const pageTitle = computed(() => `${isTable.value ? '交换任务' : '交付任务'} ${id.value}`);

const rows = computed(() => {
  const t = taskRef.value;
  if (!t) return [];
  const repo = (t.repository as Record<string, unknown> | undefined) ?? {};
  return mapDetailRows([
    { label: '任务编号', value: id.value },
    { label: '名称', value: String(t.name ?? '—') },
    { label: '状态', value: formatTodoStatus(String(t.status ?? '')) },
    { label: '渠道', value: String(t.channel ?? repo.channel ?? '—') },
    { label: '关联申请', value: String(t.requestId ?? repo.application_code ?? '—') },
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
      />
      <PhaseTrack :steps="timeline" aria-label="交付进度" />
      <DetailPanel v-if="rows.length" :title="isTable ? '交换任务详情' : '任务详情'" :rows="rows" />
      <p v-else-if="source === 'live'" class="focus-empty">{{ isTable ? '未找到该交换任务。' : '未找到该交付任务。' }}</p>
      <p v-else class="focus-empty">等待数据装载……</p>
      <DetailActions v-if="taskRef">
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
</style>
