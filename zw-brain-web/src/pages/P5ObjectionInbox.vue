<script setup lang="ts">
import { computed } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import { useProvider, useSnapshot } from '@/composables/useSnapshot';
import { getProductRole } from '@/composables/useProductRole';
import { canPerformAction } from '@/lib/pageAccess';
import { formatTodoStatus, todoStatusTone } from '@/lib/statusLabels';
import { formatObjectionType } from '@/lib/objectionLabels';
import { acceptObjectionCase } from '@/lib/objectionActions';
import { shortId, displayRecordName, isTestMarkerName } from '@/lib/userLanguage';

interface TimelineStep { stage: string; status: string; label: string; holder?: string }

const provider = useProvider();
const { source } = useSnapshot();
const role = getProductRole();

// D57①（R6）：收件箱纳入 submitted 态案件并接通受理动作（v5 异议受理=业务运营员；
// 与后端 objection.case.accept={MANAGER,BUSIAUDIT} set-equal，经 ACTION_ROLE_GATES chokepoint）。
const canAccept = computed(() => canPerformAction('objection.case.accept', role.value));

type InboxRow = {
  id: string;
  title: string;
  status: string;
  kind: string;
  holder: string;
  targetLabel: string;
  targetHref: string;
};

// G：当前段 holder（「卡在谁桌上」）——取后端现算 timeline 的 current 段，列表即可见、不必进详情。
function _currentHolder(raw: unknown): string {
  if (!Array.isArray(raw)) return '';
  const cur = (raw as TimelineStep[]).find((s) => s.status === 'current');
  return cur?.holder ?? '';
}

const items = computed((): InboxRow[] => {
  const raw = (provider.value as { objection_cases?: unknown[] }).objection_cases;
  if (!Array.isArray(raw)) return [];
  // 过滤明显的测试/样例/乱码异议行（保守判定，命中须 log，不静默吞行）。
  const kept = raw.filter((row) => !isTestMarkerName(String((row as Record<string, unknown>).title ?? '')));
  const filteredCount = raw.length - kept.length;
  if (filteredCount > 0) {
    console.debug(`[P5ObjectionInbox] 过滤测试样例异议行 ${filteredCount} 条（共 ${raw.length} 条）`);
  }
  return kept.map((row) => {
    const it = row as Record<string, unknown>;
    const id = String(it.id ?? '');
    return {
      id,
      // 名缺失 / 名==id / 名是裸 id → 「未命名异议（编码 …）」，不把 id 当标题直出（R12）。
      title: displayRecordName(it.title, id, '异议'),
      status: String(it.status ?? ''),
      kind: String(it.objection_kind ?? ''),
      holder: _currentHolder(it.statusTimeline),
      targetLabel: String(it.target_label ?? it.target_id ?? ''),
      targetHref: String(it.target_href ?? ''),
    };
  });
});

const headerMeta = computed(() => {
  if (source.value !== 'live') return '正在加载……';
  const n = items.value.length;
  if (!n) return '暂无待办理异议';
  const pending = items.value.filter((it) => it.status === 'submitted').length;
  const investigating = items.value.filter((it) => it.status !== 'submitted').length;
  if (pending && investigating) return `${pending} 条待受理 · ${investigating} 条核查中`;
  if (pending) return `${pending} 条待受理`;
  return `${investigating} 条核查中`;
});

async function accept(objectionId: string) {
  await acceptObjectionCase(objectionId);
}
</script>

<template>
  <main class="focus-page">
    <nav class="crumbs"><a href="#/provider">← 提供方管理</a></nav>
    <section class="panel">
      <PageFocusHeader title="异议响应收件箱" :meta="headerMeta" />

      <table v-if="source === 'live' && items.length" class="focus-table">
        <thead>
          <tr><th>异议编号</th><th>标题</th><th>关联对象</th><th>类型</th><th>状态</th><th>当前环节</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="it in items" :key="it.id" data-testid="objection-inbox-row">
            <td><code>{{ shortId(it.id) }}</code></td>
            <td>{{ it.title }}</td>
            <td>
              <a v-if="it.targetHref" :href="it.targetHref" class="row-link">{{ it.targetLabel || '查看对象' }}</a>
              <span v-else>{{ it.targetLabel || '—' }}</span>
            </td>
            <td>{{ it.kind ? formatObjectionType(it.kind) : '—' }}</td>
            <td><span :class="todoStatusTone(it.status)">{{ formatTodoStatus(it.status) }}</span></td>
            <!-- G：「卡在谁桌上」holder 进列表（列表不再比详情薄）；终态/不确证诚实留「—」。 -->
            <td class="holder-cell">{{ it.holder || '—' }}</td>
            <td class="row-actions">
              <button
                v-if="it.status === 'submitted' && canAccept"
                type="button"
                class="row-link-btn"
                data-testid="objection-accept-btn"
                @click="accept(it.id)"
              >受理</button>
              <a :href="`#/provider/inbox/objection/${it.id}`">{{ it.status === 'submitted' ? '查看' : '响应' }}</a>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else-if="source === 'live'" class="focus-empty">暂无待办理异议</p>
      <p v-else class="focus-empty">等待数据装载……</p>
    </section>
  </main>
</template>

<style scoped>
.row-actions { display: flex; gap: 10px; align-items: center; }
.holder-cell { color: var(--b-primary, #006be6); font-size: 13px; }
.row-link-btn { background: none; border: 0; padding: 0; color: var(--b-primary, #006be6); cursor: pointer; font-size: 13px; text-decoration: underline; }
.row-link { color: var(--b-primary, #006be6); font-size: 13px; }
</style>
