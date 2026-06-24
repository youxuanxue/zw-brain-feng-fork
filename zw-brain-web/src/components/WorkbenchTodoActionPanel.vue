<script setup lang="ts">
import { computed, reactive } from 'vue';
import DetailPanel from '@/components/DetailPanel.vue';
import DetailActions from '@/components/DetailActions.vue';
import GatedAction from '@/components/GatedAction.vue';
import { invokeActionStub, pushToast } from '@/composables/useActionStub';
import { mapDetailRows } from '@/lib/detailDisplay';
import type {
  WorkbenchTodoAction,
  WorkbenchTodoActionItem,
  WorkbenchTodoDecision,
} from '@/fixtures/workbench-fixture';

// 一条待办的行内决策面，两种形态：
//   - kind='decision'：单条记录 = 要点行（复用 DetailPanel）+ 决策按钮（整组包在 GatedAction
//     内自门控）。点击直接调 invokeActionStub——它内部失效并重拉工作台，办结待办自行消失。
//   - kind='decision-list'：聚合待办 = 逐条记录就地办理，每条 label + 紧凑要点 + 决策按钮
//     （每个按钮单独包 GatedAction，gate = decision.gate || item.gate）。
// 「驳回 / 退回」类决策可标 needsReason：先展开行内理由框，填写确认后再下发。
const props = defineProps<{ action: WorkbenchTodoAction; role: string }>();

const toneClass: Record<WorkbenchTodoDecision['tone'], string> = {
  primary: 'gov-btn-primary',
  secondary: 'gov-btn-secondary',
  danger: 'gov-btn-danger',
};

// ── 单条（decision）形态：与 M1 完全一致 ──
const rows = computed(() =>
  props.action.kind === 'decision' ? mapDetailRows(props.action.context) : []
);

// 发布类动作（catalog.entry.publish）后端每次都回 duplicate_warnings（不阻断发布，供 UI 提醒）。
// 供数据页旧发布队列退役后，重复率提醒迁到工作台行内发布——非空则 warn toast，不静默丢这条价值。
function surfaceDuplicateWarnings(result: { ok: boolean; data?: unknown }): void {
  if (!result.ok) return;
  const root = (result.data ?? {}) as Record<string, unknown>;
  const inner = (root.result ?? root) as Record<string, unknown>;
  const warnings = inner.duplicate_warnings;
  if (Array.isArray(warnings) && warnings.length) {
    pushToast({
      kind: 'warn',
      title: '发布成功 · 重复率提醒',
      detail: `检测到 ${warnings.length} 条可能重复（不阻断发布，请核对后再推广）`,
    });
  }
}

function surfaceNationalChannelResult(result: { ok: boolean; data?: unknown }): void {
  if (!result.ok) return;
  const root = (result.data ?? {}) as Record<string, unknown>;
  const inner = (root.result ?? root) as Record<string, unknown>;
  const channel = inner.national_channel as Record<string, unknown> | undefined;
  if (!channel) return;
  const status = String(channel.status ?? '');
  const reason = String(channel.reason ?? '').trim();
  if (status === 'pending' && reason) {
    pushToast({ kind: 'warn', title: '国家通道待接入', detail: reason });
  }
}

async function decide(decision: WorkbenchTodoDecision): Promise<void> {
  if (props.action.kind !== 'decision') return;
  const result = await invokeActionStub({
    skillId: decision.capability || props.action.capability,
    payload: { ...props.action.basePayload, ...decision.payload },
    successTitle: decision.success,
  });
  surfaceDuplicateWarnings(result);
  surfaceNationalChannelResult(result);
}

// ── 聚合（decision-list）形态：逐条办理 + 行内理由门 ──
const items = computed<WorkbenchTodoActionItem[]>(() =>
  props.action.kind === 'decision-list' ? props.action.items : []
);

function reasonKeyOf(decision: WorkbenchTodoDecision): string {
  return decision.reasonKey || 'reason';
}
function gateOf(item: WorkbenchTodoActionItem, decision: WorkbenchTodoDecision): string {
  return decision.gate || item.gate;
}
function rowsOf(item: WorkbenchTodoActionItem) {
  return mapDetailRows(item.context);
}

// 正在填理由的「记录+决策」复合键；同一时刻仅一处理由框展开。
const reasonFor = reactive<{ key: string; text: string }>({ key: '', text: '' });
function pairKey(item: WorkbenchTodoActionItem, idx: number): string {
  return `${item.id}::${idx}`;
}

async function actOnItem(
  item: WorkbenchTodoActionItem,
  decision: WorkbenchTodoDecision,
  idx: number
): Promise<void> {
  // 需要理由：第一次点击只展开理由框，由确认按钮真正下发。
  if (decision.needsReason && reasonFor.key !== pairKey(item, idx)) {
    reasonFor.key = pairKey(item, idx);
    reasonFor.text = '';
    return;
  }
  await dispatch(item, decision);
}

async function dispatch(
  item: WorkbenchTodoActionItem,
  decision: WorkbenchTodoDecision
): Promise<void> {
  let reasonPatch: Record<string, string> = {};
  if (decision.needsReason) {
    const text = reasonFor.text.trim();
    if (!text) {
      pushToast({
        kind: 'warn',
        title: '请先填写理由',
        detail: `${decision.label}需要说明依据，理由不能为空。`,
      });
      return;
    }
    reasonPatch = { [reasonKeyOf(decision)]: text };
  }
  const result = await invokeActionStub({
    skillId: decision.capability || item.capability,
    payload: { ...item.basePayload, ...decision.payload, ...reasonPatch },
    successTitle: decision.success,
  });
  surfaceDuplicateWarnings(result);
  surfaceNationalChannelResult(result);
  cancelReason();
}

function cancelReason(): void {
  reasonFor.key = '';
  reasonFor.text = '';
}
</script>

<template>
  <div class="todo-action-panel" data-testid="workbench-todo-action-panel">
    <!-- 单条记录：与 M1 完全一致，不动。 -->
    <template v-if="action.kind === 'decision'">
      <DetailPanel title="办理要点" :rows="rows" />
      <GatedAction :gate="action.gate" :role="role">
        <DetailActions>
          <button
            v-for="(decision, idx) in action.decisions"
            :key="idx"
            type="button"
            class="gov-btn"
            :class="toneClass[decision.tone]"
            data-testid="workbench-todo-decision"
            @click="decide(decision)"
          >
            {{ decision.label }}
          </button>
        </DetailActions>
      </GatedAction>
    </template>

    <!-- 聚合记录：逐条就地办理。 -->
    <ul v-else class="todo-item-list">
      <li
        v-for="item in items"
        :key="item.id"
        class="todo-item"
        data-testid="workbench-decision-item"
      >
        <p class="todo-item-label">{{ item.label }}</p>
        <DetailPanel v-if="item.context.length" :rows="rowsOf(item)" />
        <div class="todo-item-actions">
          <template v-for="(decision, idx) in item.decisions" :key="idx">
            <GatedAction :gate="gateOf(item, decision)" :role="role">
              <button
                type="button"
                class="gov-btn"
                :class="toneClass[decision.tone]"
                data-testid="workbench-todo-decision"
                @click="actOnItem(item, decision, idx)"
              >
                {{ decision.label }}
              </button>
            </GatedAction>
          </template>
        </div>
        <!-- 行内理由门（驳回 / 退回类）：填写后确认才真正下发。 -->
        <template v-for="(decision, idx) in item.decisions" :key="`r-${idx}`">
          <div
            v-if="decision.needsReason && reasonFor.key === pairKey(item, idx)"
            class="todo-reason-box"
          >
            <label :for="`reason-${item.id}-${idx}`">{{ decision.label }}理由（必填，将告知申请人）</label>
            <textarea
              :id="`reason-${item.id}-${idx}`"
              v-model="reasonFor.text"
              rows="3"
              placeholder="请说明依据，便于申请人理解结论或按需调整后重新发起"
              data-testid="workbench-decision-reason"
            />
            <div class="todo-reason-actions">
              <button
                type="button"
                class="gov-btn gov-btn-primary"
                data-testid="workbench-decision-reason-confirm"
                @click="dispatch(item, decision)"
              >
                确认
              </button>
              <button type="button" class="gov-btn gov-btn-secondary" @click="cancelReason">
                取消
              </button>
            </div>
          </div>
        </template>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.todo-action-panel {
  margin-top: 12px;
  padding: 14px 16px;
  border: 1px solid var(--b-border, #d4e2f4);
  border-radius: 8px;
  background: var(--b-bg-subtle, #f4f9ff);
}
/* P1 工作台不是 .focus-detail，全局 .detail-list / .detail-actions 网格不命中——
   在面内自给一份紧凑版样式，让要点行成两列、按钮成一排。 */
.todo-action-panel :deep(.detail-block) {
  padding: 0;
  margin: 0;
  border: 0;
  background: transparent;
}
.todo-action-panel :deep(.detail-block-head) {
  margin-bottom: 10px;
}
.todo-action-panel :deep(.detail-block-title) {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  line-height: 1.35;
  color: var(--b-neutral-text, #1a1d21);
}
.todo-action-panel :deep(.detail-list) {
  display: grid;
  grid-template-columns: 6rem minmax(0, 1fr);
  gap: 8px 16px;
  margin: 0;
}
.todo-action-panel :deep(.detail-list dt) {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.5;
  color: var(--b-muted, #5c6370);
}
.todo-action-panel :deep(.detail-list dd) {
  margin: 0;
  min-width: 0;
  font-size: 13px;
  line-height: 1.55;
  color: var(--b-neutral-text, #1a1d21);
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  word-break: break-word;
}
.todo-action-panel :deep(.detail-actions) {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--b-border, #d4e2f4);
}
.todo-action-panel :deep(.status-pill) {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.4;
  background: var(--b-bg-subtle, #e8f2fc);
  color: var(--b-muted, #5c6370);
}
/* 聚合形态：逐条卡片。 */
.todo-item-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.todo-item {
  padding: 12px 14px;
  border: 1px solid var(--b-border, #d4e2f4);
  border-radius: 6px;
  background: #fff;
}
.todo-item-label {
  margin: 0 0 10px;
  font-size: 14px;
  font-weight: 700;
  line-height: 1.4;
  color: var(--b-neutral-text, #1a1d21);
}
.todo-item-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--b-border, #d4e2f4);
}
.todo-reason-box {
  display: grid;
  gap: 8px;
  max-width: 640px;
  margin-top: 12px;
}
.todo-reason-box label {
  font-size: 13px;
  color: var(--b-muted, #5c6370);
}
.todo-reason-box textarea {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--b-border, #d4e2f4);
  border-radius: 6px;
  font-size: 13px;
  font-family: inherit;
}
.todo-reason-actions {
  display: flex;
  gap: 10px;
}
</style>
