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
import { deriveRecordName, formatResourceStatus, formatTime } from '@/lib/userLanguage';
import {
  typedSectionsToRows,
  decisionRows,
  compilationRows,
  catalogSummary,
} from '@/lib/typedDetailDisplay';
import { ref } from 'vue';

const route = useRoute();
const id = computed(() => String(route.params.id ?? ''));
const { resource, source, loading, fetchError } = useResourceDetail(() => id.value);
// request.create 仅 OPERATER；MANAGER/BUSIAUDIT/SECURITY_AUDIT 在 P2 详情页不渲染「申请资源」。
// A1（0605#1）：详情页对「待发布」资源仍可达，但只有「已发布（active）」才可申请——
// 叠加状态门控，未发布态不渲染申请按钮（守「只有已发布才可供申请使用」）。
// 详情 status 可能是原始 lifecycle（record_to_card_dict 给 "active"）或展示词（快照回退给 "可复用"），
// 两种来源都接受，非已发布态（approved_pending_publish/待发布 等）一律拦下。
const APPLICABLE_STATUSES = new Set(['active', '可复用']);
const canApply = computed(
  () =>
    canPerformAction('request.create', getProductRole().value) &&
    APPLICABLE_STATUSES.has(String(resource.value?.status ?? '')),
);

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

// A2（0605#2）：去掉与「共享与复用」字段重复的「基本信息」缩略块（提供方等已在决策块），
// 只把真正独有、轻量的事实（状态/最近更新/订阅量）收进 header 下一行细条，
// 首屏直达决策视图，消除「先缩略再详情」的跳跃感。
const headerFacts = computed(() => {
  const r = resource.value;
  if (!r) return [] as string[];
  const out: string[] = [];
  // R12：status 可能是快照中文（可复用）或 resource_view 富集回的原始 lifecycle（draft/active…），
  // 统一经 formatResourceStatus 映射，绝不裸出工程态。
  if (r.status) out.push(`状态 ${formatResourceStatus(r.status)}`);
  if (r.updatedAt) out.push(`最近更新 ${formatTime(r.updatedAt)}`);
  if (r.subscribers !== undefined) out.push(`订阅 ${String(r.subscribers)}`);
  return out;
});

const fields = computed(() => (Array.isArray(resource.value?.fields) ? (resource.value!.fields as string[]) : []));
const explain = computed(() => (Array.isArray(resource.value?.explain) ? (resource.value!.explain as string[]) : []));

// 反馈 6 — 分型块（库表→库表信息 / 文件→文件信息 / 接口→接口信息 / 链接→链接信息）。
const typedSections = computed(() =>
  typedSectionsToRows(resource.value?.typedDetail as Parameters<typeof typedSectionsToRows>[0]),
);
const typedDetailRows = computed(() =>
  typedSections.value.map((sec) => ({ title: sec.title, rows: mapDetailRows(sec.rows) })),
);
const kindLabel = computed(() => String((resource.value?.typedDetail as Record<string, unknown> | undefined)?.kindLabel ?? ''));

// 反馈 5 — 首屏决策字段 + 折叠编目字段（编制规范全集）+ 摘要。
const accessPolicy = computed(() => (resource.value?.accessPolicy as Record<string, unknown> | undefined) ?? null);
const catalogMeta = computed(() => (resource.value?.catalogMeta as Record<string, unknown> | undefined) ?? null);
const decisionDetailRows = computed(() => decisionRows(accessPolicy.value, catalogMeta.value));
const compilationDetailRows = computed(() => compilationRows(catalogMeta.value));
const summaryText = computed(() => catalogSummary(catalogMeta.value));

// 编目字段默认折叠（不抢首屏决策视野），点击展开看全量编制规范字段。
const showCompilation = ref(false);

const headerTitle = computed(() => {
  if (resource.value) return deriveRecordName(displayName.value, id.value, '数据资源');
  if (loading.value) return '正在加载……';
  return deriveRecordName('', id.value, '数据资源');
});
const headerMeta = computed(() => {
  if (resource.value && resource.value.desc) return String(resource.value.desc);
  if (fetchError.value) return '暂时无法加载资源详情，请稍后再试。';
  if (source.value !== 'live') return '正在加载资源详情……';
  if (!resource.value) return '未找到该资源';
  return '';
});

// 申请采草稿流（0605#8）：先生成草稿单（不直接提交），跳到申请详情页让用户查看 / 确认，
// 确认无误后在详情页手动「确认提交申请」才进入审批。
async function apply() {
  const result = await invokeActionStub({
    skillId: 'request.create',
    payload: { resource_id: id.value },
    successTitle: '申请草稿已生成，请在详情页确认后提交',
  });
  const requestId = resolveRequestIdFromAction(result);
  if (requestId) navigateToRequestDetail(requestId);
}
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/discovery">← 资源发现</a></nav>
    <section class="panel">
      <PageFocusHeader :title="headerTitle" :meta="headerMeta">
        <template v-if="kindLabel" #aside>
          <span class="kind-badge" data-testid="resource-kind-badge">{{ kindLabel }}</span>
        </template>
      </PageFocusHeader>
      <p v-if="headerFacts.length" class="detail-facts" data-testid="detail-facts">{{ headerFacts.join(' · ') }}</p>

      <!-- 反馈 5 首屏：决策字段（共享/更新/提供方）+ 摘要，用户看完即可决定要不要申请 -->
      <DetailPanel
        v-if="decisionDetailRows.length"
        title="共享与复用"
        :rows="decisionDetailRows"
        data-testid="decision-block"
      />
      <section v-if="summaryText" class="detail-block" data-testid="summary-block">
        <h2 class="detail-block-title">数据资源摘要</h2>
        <p class="summary-text">{{ summaryText }}</p>
      </section>

      <!-- 反馈 6 分型块：按资源类型展示各自详情（文件信息 / 库表信息 / 接口信息 / 链接信息） -->
      <DetailPanel
        v-for="sec in typedDetailRows"
        :key="sec.title"
        :title="sec.title"
        :rows="sec.rows"
        data-testid="typed-detail-block"
      />

      <section v-if="fields.length" class="detail-block">
        <h2 class="detail-block-title">{{ fields.length > 12 ? `字段清单（前 12 项，共 ${fields.length} 项）` : `字段清单（${fields.length} 项）` }}</h2>
        <ul class="chip-list">
          <li v-for="f in fields.slice(0, 12)" :key="f">{{ f }}</li>
        </ul>
      </section>
      <section v-if="canViewSchema" class="detail-block" data-testid="resource-schema-block">
        <h2 class="detail-block-title">字段数据模型</h2>
        <p v-if="schemaLoading" class="schema-state" data-testid="resource-schema-loading">正在加载字段数据模型……</p>
        <p v-else-if="schemaError" class="schema-state schema-state-error" data-testid="resource-schema-error">
          字段信息暂未提供，请稍后再试或联系数据提供方。
        </p>
        <p v-else-if="schemaEmpty" class="schema-state" data-testid="resource-schema-empty">该资源暂无登记的字段数据模型。</p>
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
      <!-- 反馈 5 折叠：编制规范编目字段全集（目录代码/格式/来源/领域 …），默认收起不抢首屏 -->
      <section v-if="compilationDetailRows.length" class="detail-block" data-testid="compilation-block">
        <button
          type="button"
          class="collapse-toggle"
          :aria-expanded="showCompilation"
          data-testid="compilation-toggle"
          @click="showCompilation = !showCompilation"
        >
          <span>编目信息（目录编制规范字段）</span>
          <span class="collapse-arrow">{{ showCompilation ? '收起' : '展开' }}</span>
        </button>
        <DetailPanel v-if="showCompilation" :rows="compilationDetailRows" />
      </section>

      <DetailActions>
        <button v-if="canApply" type="button" class="gov-btn gov-btn-primary" data-skill="request.create" @click="apply">申请资源</button>
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
.kind-badge { display: inline-block; font-size: 13px; padding: 3px 12px; border-radius: 999px; background: var(--b-bg-subtle, #e8f2fc); color: var(--b-primary, #006be6); border: 1px solid var(--b-border, #d4e2f4); }
.detail-facts { margin: 4px 0 0; font-size: 13px; color: var(--b-text-muted, #5b6b7f); }
.summary-text { margin: 8px 0 0; font-size: 14px; line-height: 1.7; color: var(--b-neutral-text, #1a1d21); }
.collapse-toggle { display: flex; align-items: center; justify-content: space-between; width: 100%; padding: 8px 0; background: none; border: none; cursor: pointer; font-size: 15px; font-weight: 600; color: var(--b-neutral-text, #1a1d21); }
.collapse-arrow { font-size: 13px; font-weight: 400; color: var(--b-primary, #006be6); }
</style>
