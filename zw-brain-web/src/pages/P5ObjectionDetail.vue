<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRoute } from 'vue-router';
import { invokeActionStub } from '@/composables/useActionStub';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailPanel from '@/components/DetailPanel.vue';
import DetailActions from '@/components/DetailActions.vue';
import { useDisputes, useSnapshot } from '@/composables/useSnapshot';
import { mapDetailRows } from '@/lib/detailDisplay';
import { formatTodoStatus } from '@/lib/statusLabels';

const route = useRoute();
const id = computed(() => String(route.params.id ?? ''));
const disputes = useDisputes();
const { source } = useSnapshot();
const opinion = ref('已核实，准备修正相关描述');

const dispute = computed(() => {
  const list = disputes.value;
  if (!Array.isArray(list)) return null;
  return (
    list.find((row) => String((row as Record<string, unknown>).id ?? '') === id.value) as
      | Record<string, unknown>
      | undefined
  ) ?? null;
});

const rows = computed(() => {
  const d = dispute.value;
  if (!d) {
    return mapDetailRows([
      { label: '异议编号', value: id.value },
      { label: '状态', value: '未在待办列表中找到' },
    ]);
  }
  const repo = (d.repository as Record<string, unknown> | undefined) ?? {};
  return mapDetailRows([
    { label: '异议编号', value: id.value },
    { label: '标题', value: String(d.title ?? d.topic ?? '—') },
    { label: '状态', value: formatTodoStatus(String(repo.status ?? d.status ?? '')) },
    { label: '对象类型', value: String(d.targetType ?? repo.targetType ?? '—') },
    { label: '对象编号', value: String(d.targetId ?? '—') },
  ]);
});

const headerMeta = computed(() => {
  if (dispute.value) return '提交回复后进入复核环节';
  if (source.value === 'live') return '当前列表中无此异议';
  return '正在加载……';
});

async function submitReply() {
  await invokeActionStub({
    skillId: 'objection.case.reply',
    payload: {
      objection_id: id.value,
      node_name: '提供方部门核查回复',
      opinion: opinion.value,
      action_result: 'submitted',
    },
    successTitle: '已提交提供方回复',
    role: 'ROLE_ORGAN_MANAGER',
    refreshSnapshotAfter: true,
  });
}

async function markResolved() {
  await invokeActionStub({
    skillId: 'objection.case.review',
    payload: {
      objection_id: id.value,
      decision: 'resolve',
      resolved_summary: opinion.value,
    },
    successTitle: '异议已标记为已解决',
    role: 'ROLE_ORGAN_MANAGER',
    refreshSnapshotAfter: true,
  });
}
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/provider/inbox/objection">← 异议响应收件箱</a></nav>
    <section class="panel">
      <PageFocusHeader :title="`异议 ${id}`" :meta="headerMeta" />
      <DetailPanel title="基本信息" :rows="rows" />
      <div class="opinion-box">
        <label for="opinion">回复意见</label>
        <textarea id="opinion" v-model="opinion" rows="4" />
      </div>
      <DetailActions>
        <button type="button" class="gov-btn gov-btn-primary" @click="submitReply">提交回复</button>
        <button type="button" class="gov-btn" @click="markResolved">标记已解决</button>
      </DetailActions>
    </section>
  </main>
</template>

<style scoped>
.opinion-box { margin-top: 12px; display: grid; gap: 6px; }
label { font-size: 13px; color: var(--b-muted, #5c6370); }
textarea {
  width: 100%;
  max-width: 560px;
  padding: 8px 10px;
  border: 1px solid var(--b-border, #d4e2f4);
  border-radius: 6px;
  font-size: 14px;
}
.gov-btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid var(--b-border, #d4e2f4); background: #fff; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; border-color: transparent; }
</style>
