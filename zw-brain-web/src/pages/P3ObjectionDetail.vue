<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailPanel from '@/components/DetailPanel.vue';
import DetailActions from '@/components/DetailActions.vue';
import { authFetch } from '@/composables/useAuth';
import { invokeActionStub } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';
import { mapDetailRows } from '@/lib/detailDisplay';
import { formatTodoStatus } from '@/lib/statusLabels';
import { formatObjectionType, objectionTargetHref } from '@/lib/objectionLabels';
import { apiUrl } from '@/composables/useApiBase';

const route = useRoute();
const id = computed(() => String(route.params.id ?? ''));
const caseRow = ref<Record<string, unknown> | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);
const score = ref(5);
const comment = ref('处理及时，结果满意');
const role = getProductRole();

async function loadCase() {
  loading.value = true;
  error.value = null;
  try {
    const resp = await authFetch(apiUrl('/api/skills/objection.case.query'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ role: role.value, confirmed: true }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const payload = (await resp.json()) as { items?: Record<string, unknown>[] };
    caseRow.value =
      (payload.items ?? []).find((row) => String(row.id ?? '') === id.value) ?? null;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

onMounted(() => { void loadCase(); });

const status = computed(() => String(caseRow.value?.status ?? ''));

const rows = computed(() => {
  const c = caseRow.value;
  if (!c) return mapDetailRows([{ label: '异议编号', value: id.value }, { label: '状态', value: '未找到' }]);
  const tType = String(c.target_type ?? c.targetType ?? '—');
  const tId = String(c.target_id ?? c.targetId ?? '—');
  return mapDetailRows([
    { label: '异议编号', value: id.value },
    { label: '标题', value: String(c.title ?? '—') },
    { label: '状态', value: formatTodoStatus(status.value) },
    { label: '对象类型', value: formatObjectionType(tType) },
    { label: '对象编号', value: tId, href: objectionTargetHref(tType, tId) },
  ]);
});

const headerMeta = computed(() => {
  if (loading.value) return '正在加载……';
  if (error.value) return error.value;
  if (!caseRow.value) return '未找到该异议';
  return `当前：${formatTodoStatus(status.value)}`;
});

const canSubmit = computed(() => status.value === 'draft');
const canEvaluate = computed(() => status.value === 'resolved');
const canClose = computed(
  () =>
    status.value === 'resolved' &&
    ['ROLE_ORGAN_MANAGER', 'ROLE_BUSIAUDIT', 'ROLE_SECURITY_AUDIT'].includes(role.value),
);

async function submitCase() {
  await invokeActionStub({
    skillId: 'objection.case.submit',
    payload: { objection_id: id.value },
    successTitle: '异议已提交',
    refreshSnapshotAfter: true,
  });
  await loadCase();
}

async function evaluateCase() {
  await invokeActionStub({
    skillId: 'objection.case.evaluate',
    payload: {
      objection_id: id.value,
      solved_flag: true,
      overall_score: score.value,
      comment: comment.value,
    },
    successTitle: '评价已提交',
    refreshSnapshotAfter: true,
  });
  await loadCase();
}

async function closeCase() {
  await invokeActionStub({
    skillId: 'objection.case.close',
    payload: { objection_id: id.value },
    successTitle: '异议已归档',
    refreshSnapshotAfter: true,
  });
  await loadCase();
}
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/request-flow/objection">← 我的异议</a></nav>
    <section class="panel">
      <PageFocusHeader :title="`异议 ${id}`" :meta="headerMeta" />
      <DetailPanel title="基本信息" :rows="rows" />
      <div v-if="canEvaluate" class="opinion-box">
        <label for="score">满意度（1-5）</label>
        <input id="score" v-model.number="score" type="number" min="1" max="5" />
        <label for="comment">评价说明</label>
        <textarea id="comment" v-model="comment" rows="3" />
      </div>
      <DetailActions>
        <button v-if="canSubmit" type="button" class="gov-btn gov-btn-primary" @click="submitCase">提交至平台</button>
        <button v-if="canEvaluate" type="button" class="gov-btn gov-btn-primary" @click="evaluateCase">提交评价</button>
        <button v-if="canClose" type="button" class="gov-btn gov-btn-secondary" @click="closeCase">归档关闭</button>
      </DetailActions>
    </section>
  </main>
</template>

<style scoped>
.opinion-box { margin-top: 12px; display: grid; gap: 6px; max-width: 560px; }
label { font-size: 13px; color: var(--b-muted, #5c6370); }
textarea, input { padding: 8px 10px; border: 1px solid var(--b-border, #d4e2f4); border-radius: 6px; }
.gov-btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid var(--b-border, #d4e2f4); background: #fff; margin-right: 8px; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; border-color: transparent; }
</style>
