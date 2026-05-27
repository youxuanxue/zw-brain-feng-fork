<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailPanel from '@/components/DetailPanel.vue';
import DetailActions from '@/components/DetailActions.vue';
import { lookupDeliveryTask, useSnapshot } from '@/composables/useSnapshot';
import { invokeActionStub } from '@/composables/useActionStub';
import { mapDetailRows } from '@/lib/detailDisplay';
import { formatTodoStatus } from '@/lib/statusLabels';

const route = useRoute();
const id = computed(() => String(route.params.id ?? ''));
const taskRef = lookupDeliveryTask(id.value);
const { source } = useSnapshot();

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
  if (!taskRef.value) return '未找到该交付任务';
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
    successTitle: '已触发对账',
  });
}
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/delivery-exchange">← 交付任务列表</a></nav>
    <section class="panel">
      <PageFocusHeader
        :title="`交付任务 ${id}`"
        :meta="headerMeta"
        :links="[{ label: '提异议', href: objectionLink }]"
      />
      <DetailPanel v-if="rows.length" title="任务详情" :rows="rows" />
      <p v-else-if="source === 'live'" class="focus-empty">未找到该交付任务。</p>
      <p v-else class="focus-empty">等待数据装载……</p>
      <DetailActions v-if="taskRef">
        <button type="button" class="gov-btn gov-btn-secondary" @click="openCredential">领凭据</button>
        <button type="button" class="gov-btn gov-btn-primary" @click="reconcile">对账回执</button>
      </DetailActions>
    </section>
  </main>
</template>

<style scoped>
.gov-btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid transparent; margin-right: 8px; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-secondary { background: #fff; border-color: var(--b-border, #d4e2f4); }
</style>
