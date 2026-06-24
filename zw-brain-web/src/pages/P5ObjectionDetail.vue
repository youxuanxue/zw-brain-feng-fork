<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRoute } from 'vue-router';
import { invokeActionStub, pushToast } from '@/composables/useActionStub';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailPanel from '@/components/DetailPanel.vue';
import DetailActions from '@/components/DetailActions.vue';
import PhaseTrack from '@/components/PhaseTrack.vue';
import { useDisputes, useSnapshot } from '@/composables/useSnapshot';
import { mapDetailRows } from '@/lib/detailDisplay';
import { formatTodoStatus } from '@/lib/statusLabels';
import { getProductRole } from '@/composables/useProductRole';
import { canPerformAction } from '@/lib/pageAccess';
import { acceptObjectionCase } from '@/lib/objectionActions';
import { formatObjectionType, providerObjectionTargetHref } from '@/lib/objectionLabels';

interface TimelineStep { stage: string; status: string; label: string; holder?: string }

const route = useRoute();
const id = computed(() => String(route.params.id ?? ''));
const disputes = useDisputes();
const { source } = useSnapshot();
const role = getProductRole();
// 异议办理是最需要真实表态的环节，默认空白、等待办理人亲笔填写；不预置成品口径。
const opinion = ref('');

function requireOpinion(): boolean {
  if (opinion.value.trim()) return true;
  pushToast({ kind: 'warn', title: '请填写回复意见', detail: '需要写明核实结论与处理意见后才能提交。' });
  return false;
}

const dispute = computed(() => {
  const list = disputes.value;
  if (!Array.isArray(list)) return null;
  return (
    list.find((row) => String((row as Record<string, unknown>).id ?? '') === id.value) as
      | Record<string, unknown>
      | undefined
  ) ?? null;
});

// G 脊柱：异议办理 timeline（后端 dispute_snapshot 现算，前端不重派生）；支线态（驳回）给 note。
const timeline = computed<TimelineStep[]>(() => {
  const raw = (dispute.value?.statusTimeline ?? []) as unknown;
  return Array.isArray(raw) ? (raw as TimelineStep[]) : [];
});
const lifecycleNote = computed(() => String(dispute.value?.lifecycleNote ?? ''));

const rows = computed(() => {
  const d = dispute.value;
  if (!d) {
    return mapDetailRows([
      { label: '异议编号', value: id.value },
      { label: '状态', value: '未在待办列表中找到' },
    ]);
  }
  const repo = (d.repository as Record<string, unknown> | undefined) ?? {};
  const targetType = String(d.targetType ?? repo.targetType ?? '');
  const targetId = String(d.targetId ?? '');
  const targetLabel = String(d.targetLabel ?? (targetId || '—'));
  return mapDetailRows([
    { label: '异议编号', value: id.value },
    { label: '标题', value: String(d.title ?? d.topic ?? '—') },
    { label: '状态', value: formatTodoStatus(String(repo.status ?? d.status ?? '')) },
    { label: '对象类型', value: targetType ? formatObjectionType(targetType) : '—' },
    {
      label: '对象编号',
      value: targetLabel,
      href: String(d.targetHref ?? '') || providerObjectionTargetHref(targetType, targetId),
    },
  ]);
});

// D57①（R6）：submitted 态先受理（objection.case.accept，受理即进入平台核查）；
// 受理前不渲染回复/解决动作（submitted → resolved 非法迁移，渲染=必 409 死按钮）。
const rawStatus = computed(() => {
  const d = dispute.value;
  if (!d) return '';
  const repo = (d.repository as Record<string, unknown> | undefined) ?? {};
  return String(repo.status ?? d.status ?? '');
});
const isPendingAccept = computed(() => rawStatus.value === 'submitted');
const canAccept = computed(() => canPerformAction('objection.case.accept', role.value));
// 原 B11 督办孤儿页（零入口）折叠：升级督办归位异议处理方面，角色门与原 B11 一致（决策见 route-table）。
const canEscalate = computed(() => canPerformAction('objection.case.escalate', role.value));

const headerMeta = computed(() => {
  if (dispute.value) return isPendingAccept.value ? '受理后进入核查环节' : '提交回复后进入复核环节';
  if (source.value === 'live') return '当前列表中无此异议';
  return '正在加载……';
});

async function acceptCase() {
  await acceptObjectionCase(id.value);
}

async function submitReply() {
  if (!requireOpinion()) return;
  await invokeActionStub({
    skillId: 'objection.case.reply',
    payload: {
      objection_id: id.value,
      node_name: '提供方部门核查回复',
      opinion: opinion.value.trim(),
      action_result: 'submitted',
    },
    successTitle: '已提交提供方回复',
    refreshSnapshotAfter: true,
  });
}

async function markResolved() {
  if (!requireOpinion()) return;
  await invokeActionStub({
    skillId: 'objection.case.review',
    payload: {
      objection_id: id.value,
      decision: 'resolve',
      resolved_summary: opinion.value.trim(),
    },
    successTitle: '异议已标记为已解决',
    refreshSnapshotAfter: true,
  });
}

// 升级督办——事件式过程标记，不改 case.status（objection.case.escalate 后端零改动）。
// 升级复用主回复意见（同一份核实结论），不另设独立理由框、不写死成品口径；空则拦截。
async function escalate() {
  if (!requireOpinion()) return;
  await invokeActionStub({
    skillId: 'objection.case.escalate',
    payload: { objection_id: id.value, opinion: opinion.value.trim() },
    successTitle: '已升级督办',
    refreshSnapshotAfter: true,
  });
}
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/provider/inbox/objection">← 异议响应收件箱</a></nav>
    <section class="panel">
      <PageFocusHeader :title="`异议 ${id}`" :meta="headerMeta" />
      <!-- G 脊柱：办理进度（提交→受理→核查→办结→归档）「卡在谁桌上」。支线态（驳回）走 note。 -->
      <PhaseTrack v-if="timeline.length" :steps="timeline" aria-label="异议办理进度" />
      <p v-else-if="lifecycleNote" class="lifecycle-note">当前：{{ lifecycleNote }}</p>
      <DetailPanel title="基本信息" :rows="rows" />
      <DetailActions v-if="isPendingAccept">
        <button
          v-if="canAccept"
          type="button"
          class="gov-btn gov-btn-primary"
          data-testid="objection-detail-accept-btn"
          @click="acceptCase"
        >受理</button>
      </DetailActions>
      <template v-if="dispute && !isPendingAccept">
        <div class="opinion-box">
          <label for="opinion">回复意见</label>
          <textarea
            id="opinion"
            v-model="opinion"
            rows="4"
            placeholder="请填写核实结论与处理意见"
          />
        </div>
        <DetailActions>
          <button type="button" class="gov-btn gov-btn-primary" @click="submitReply">提交回复</button>
          <button type="button" class="gov-btn" @click="markResolved">标记已解决</button>
          <button v-if="canEscalate" type="button" class="gov-btn gov-btn-secondary" @click="escalate">升级督办</button>
        </DetailActions>
      </template>
    </section>
  </main>
</template>

<style scoped>
.opinion-box { margin-top: 12px; display: grid; gap: 6px; }
.lifecycle-note { margin: 4px 0 12px; font-size: 13px; color: var(--b-muted, #5c6370); }
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
