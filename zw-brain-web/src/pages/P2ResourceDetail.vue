<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import { useResourceDetail } from '@/composables/useResourceDetail';
import { useResourceSchema } from '@/composables/useResourceSchema';
import { invokeActionStub } from '@/composables/useActionStub';
import { navigateToRequestDetail, resolveRequestIdFromAction } from '@/composables/useRequestNavigation';
import { getProductRole } from '@/composables/useProductRole';
import { canPerformAction } from '@/lib/pageAccess';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailPanel from '@/components/DetailPanel.vue';
import DetailActions from '@/components/DetailActions.vue';
import { mapDetailRows } from '@/lib/detailDisplay';

const route = useRoute();
const id = computed(() => String(route.params.id ?? ''));
const { resource, source, loading, fetchError } = useResourceDetail(() => id.value);
// request.create 仅 OPERATER；MANAGER/BUSIAUDIT/SECURITY_AUDIT 在 P2 详情页不渲染「发起复用申请」
const canApply = computed(() => canPerformAction('request.create', getProductRole().value));

// 字段数据模型（只读）：metadata.schema.query → MANAGER / BUSIAUDIT / SECURITY_AUDIT。
// 无权岗位（OPERATER）整块不渲染（无权=不可见），也不发请求。
const canViewSchema = computed(() => canPerformAction('metadata.schema.query', getProductRole().value));
const {
  columns: schemaColumns,
  loading: schemaLoading,
  fetchError: schemaError,
  isEmpty: schemaEmpty,
} = useResourceSchema(
  () => id.value,
  () => canViewSchema.value,
  () => getProductRole().value,
);

const displayName = computed(() => {
  const r = resource.value;
  if (!r) return '';
  return String(r.name ?? r.title ?? '');
});

const rows = computed(() => {
  const r = resource.value;
  if (!r) return [];
  const out: { label: string; value: string }[] = [];
  if (r.provider) out.push({ label: '提供方', value: String(r.provider) });
  if (r.zone) out.push({ label: '归属专题', value: String(r.zone) });
  if (r.status) out.push({ label: '当前状态', value: String(r.status) });
  if (r.updatedAt) out.push({ label: '最近更新', value: String(r.updatedAt) });
  if (r.subscribers !== undefined) out.push({ label: '订阅量', value: String(r.subscribers) });
  if (r.coverage) out.push({ label: '字段覆盖', value: String(r.coverage) });
  if (r.approvalRate) out.push({ label: '审批通过率', value: String(r.approvalRate) });
  return mapDetailRows(out);
});

const fields = computed(() => (Array.isArray(resource.value?.fields) ? (resource.value!.fields as string[]) : []));
const explain = computed(() => (Array.isArray(resource.value?.explain) ? (resource.value!.explain as string[]) : []));

const headerTitle = computed(() => {
  if (resource.value) return displayName.value || id.value;
  if (loading.value) return '正在加载……';
  return id.value;
});
const headerMeta = computed(() => {
  if (resource.value && resource.value.desc) return String(resource.value.desc);
  if (fetchError.value) return `加载失败：${fetchError.value}`;
  if (source.value !== 'live') return '正在加载资源详情……';
  if (!resource.value) return '未找到该资源';
  return '';
});

async function apply() {
  const result = await invokeActionStub({
    skillId: 'request.create',
    payload: { resource_id: id.value },
    successTitle: '复用申请已起草',
    pendingBackend: 'E2 申请管理 (e2/plan.yaml F4)',
  });
  const requestId = resolveRequestIdFromAction(result);
  if (requestId) navigateToRequestDetail(requestId);
}
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/discovery">← 资源发现</a></nav>
    <section class="panel">
      <PageFocusHeader :title="headerTitle" :meta="headerMeta" />
      <DetailPanel v-if="rows.length" title="基本信息" :rows="rows" />
      <section v-if="fields.length" class="detail-block">
        <h2 class="detail-block-title">字段清单（前 12 项）</h2>
        <ul class="chip-list">
          <li v-for="f in fields.slice(0, 12)" :key="f">{{ f }}</li>
        </ul>
      </section>
      <section v-if="canViewSchema" class="detail-block" data-testid="resource-schema-block">
        <h2 class="detail-block-title">字段数据模型</h2>
        <p v-if="schemaLoading" class="schema-state">正在加载字段数据模型……</p>
        <p v-else-if="schemaError" class="schema-state schema-state-error">
          字段数据模型加载失败：{{ schemaError }}
        </p>
        <p v-else-if="schemaEmpty" class="schema-state">该资源暂无登记的字段数据模型。</p>
        <table v-else-if="schemaColumns.length" class="schema-table" data-testid="resource-schema-table">
          <thead>
            <tr>
              <th>字段</th>
              <th>释义</th>
              <th>格式</th>
              <th>长度</th>
              <th>约束</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="col in schemaColumns" :key="col.column">
              <td class="schema-col">{{ col.column }}</td>
              <td>{{ col.comment || '—' }}</td>
              <td>{{ col.format || '—' }}</td>
              <td>{{ col.length || '—' }}</td>
              <td>
                <span v-if="col.isPrimaryKey" class="schema-tag schema-tag-pk">主键</span>
                <span v-if="!col.nullable" class="schema-tag">必填</span>
                <span v-if="col.needEncrypt" class="schema-tag schema-tag-enc">需加密</span>
              </td>
            </tr>
          </tbody>
        </table>
      </section>
      <section v-if="explain.length" class="detail-block">
        <h2 class="detail-block-title">复用提示</h2>
        <ul class="hint-list">
          <li v-for="e in explain" :key="e">{{ e }}</li>
        </ul>
      </section>
      <DetailActions>
        <button v-if="canApply" type="button" class="gov-btn gov-btn-primary" data-skill="request.create" @click="apply">发起复用申请</button>
        <a href="#/zones-pack" class="gov-btn gov-btn-secondary">看专题</a>
      </DetailActions>
    </section>
  </main>
</template>

<style scoped>
.chip-list { list-style: none; padding: 0; margin: 8px 0 0; display: flex; flex-wrap: wrap; gap: 6px; }
.chip-list li { font-size: 12px; padding: 2px 10px; background: var(--b-bg-page, #f2f7fd); border: 1px solid var(--b-border, #d4e2f4); border-radius: 999px; }
.hint-list { padding-left: 20px; margin: 8px 0 0; font-size: 14px; line-height: 1.6; }
.hint-list li { padding: 4px 0; }
.schema-state { margin: 8px 0 0; font-size: 13px; color: var(--b-text-muted, #5b6b7f); }
.schema-state-error { color: var(--b-danger, #c0392b); }
.schema-table { width: 100%; margin: 8px 0 0; border-collapse: collapse; font-size: 13px; }
.schema-table th, .schema-table td { text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--b-border, #e3ebf5); vertical-align: top; }
.schema-table th { font-weight: 600; color: var(--b-text-muted, #5b6b7f); background: var(--b-bg-page, #f7fafe); }
.schema-col { font-family: var(--b-mono, ui-monospace, SFMono-Regular, Menlo, monospace); }
.schema-tag { display: inline-block; font-size: 11px; padding: 1px 8px; margin: 0 4px 2px 0; border-radius: 999px; background: var(--b-bg-page, #f2f7fd); border: 1px solid var(--b-border, #d4e2f4); }
.schema-tag-pk { background: #eaf4ff; border-color: #b6d8ff; }
.schema-tag-enc { background: #fff3e6; border-color: #ffd5a8; }
</style>
