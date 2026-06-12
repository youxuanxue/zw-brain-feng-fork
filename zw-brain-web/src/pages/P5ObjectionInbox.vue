<script setup lang="ts">
import { computed } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import { useProvider, useSnapshot } from '@/composables/useSnapshot';
import { invokeActionStub } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';
import { canPerformAction } from '@/lib/pageAccess';
import { formatTodoStatus, todoStatusTone } from '@/lib/statusLabels';
import { shortId } from '@/lib/userLanguage';

const provider = useProvider();
const { source } = useSnapshot();
const role = getProductRole();

// D57①（R6）：收件箱纳入 submitted 态案件并接通受理动作（v5 异议受理=业务运营员；
// 与后端 objection.case.accept={MANAGER,BUSIAUDIT} set-equal，经 ACTION_ROLE_GATES chokepoint）。
const canAccept = computed(() => canPerformAction('objection.case.accept', role.value));

type InboxRow = { id: string; title: string; status: string };

const items = computed((): InboxRow[] => {
  const raw = (provider.value as { objection_cases?: unknown[] }).objection_cases;
  if (!Array.isArray(raw)) return [];
  return raw.map((row) => {
    const it = row as Record<string, unknown>;
    return {
      id: String(it.id ?? ''),
      title: String(it.title ?? it.id ?? ''),
      status: String(it.status ?? ''),
    };
  });
});

const headerMeta = computed(() => {
  if (source.value !== 'live') return '正在加载……';
  const n = items.value.length;
  if (!n) return '暂无待办理异议';
  const pending = items.value.filter((it) => it.status === 'submitted').length;
  return pending ? `${n} 条在办异议（${pending} 条待受理）` : `${n} 条在办异议`;
});

async function accept(objectionId: string) {
  await invokeActionStub({
    skillId: 'objection.case.accept',
    payload: { objection_id: objectionId },
    successTitle: '异议已受理，进入核查',
    refreshSnapshotAfter: true,
  });
}
</script>

<template>
  <main class="focus-page">
    <nav class="crumbs"><a href="#/provider">← 提供方管理</a></nav>
    <section class="panel">
      <PageFocusHeader title="异议响应收件箱" :meta="headerMeta" />

      <table v-if="source === 'live' && items.length" class="focus-table">
        <thead>
          <tr><th>异议编号</th><th>标题</th><th>状态</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="it in items" :key="it.id" data-testid="objection-inbox-row">
            <td><code>{{ shortId(it.id) }}</code></td>
            <td>{{ it.title }}</td>
            <td><span :class="todoStatusTone(it.status)">{{ formatTodoStatus(it.status) }}</span></td>
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
.row-link-btn { background: none; border: 0; padding: 0; color: var(--b-primary, #006be6); cursor: pointer; font-size: 13px; text-decoration: underline; }
</style>
