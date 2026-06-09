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
import { deriveRecordName, formatTime } from '@/lib/userLanguage';
import {
  typedSectionsToRows,
  decisionRows,
  compilationRows,
  catalogSummary,
  DECISION_SECTION_TITLE,
} from '@/lib/typedDetailDisplay';
import { ref } from 'vue';

const route = useRoute();
const id = computed(() => String(route.params.id ?? ''));
const { resource, loading, fetchError } = useResourceDetail(() => id.value);
// request.create 仅 OPERATER；MANAGER/BUSIAUDIT/SECURITY_AUDIT 在 P2 详情页不渲染「申请资源」。
// A1（0605#1）：详情页对「待发布」资源仍可达，但只有「已发布（机器值 active）」才可申请——
// 叠加状态门控（比对机器值 lifecycleStatus 而非中文展示词，单一事实源），非 active 一律拦下。
const canApply = computed(
  () =>
    canPerformAction('request.create', getProductRole().value) &&
    String(resource.value?.lifecycleStatus ?? '') === 'active',
);

// 资源物化形态（canonical kind，T4）：字段清单 / 字段数据模型仅对「库表」资源有意义；
// 文件 / 接口资源不该错显库表字段模型块（旧平台文件资源详情无「字段数据信息」）。
const resourceKind = computed(() =>
  String(
    (resource.value?.typedDetail as Record<string, unknown> | undefined)?.kind ??
      resource.value?.resourceKind ??
      '',
  ),
);
const isTable = computed(() => resourceKind.value === 'table');

// 字段数据模型（只读）：metadata.schema.query → MANAGER / BUSIAUDIT / SECURITY_AUDIT。
// 无权岗位（OPERATER）整块不渲染（无权=不可见），也不发请求。叠加 kind==='table' 门控：
// 非库表资源既不渲染也不发 schema 请求（T4 消除文件类错显）。
const canViewSchema = computed(() => canPerformAction('metadata.schema.query', getProductRole().value) && isTable.value);
// T1（6.5#2）：该块默认折叠——把异步加载推迟到用户点击展开时才发起，从根上消除「与主详情并发
// 竞速、先渲染加载态再切成表格」的二次撑高（仅有权且库表岗位会渲染本块，正是验收看到跳跃的角色）。
// enabled 同时门控「有权 ∧ 库表 ∧ 已展开」：折叠态零请求，展开即按需加载。
const showSchema = ref(false);
const {
  columns: schemaColumns,
  loading: schemaLoading,
  fetchError: schemaError,
  isEmpty: schemaEmpty,
} = useResourceSchema(
  () => id.value,
  () => canViewSchema.value && showSchema.value,
  () => getProductRole().value,
);

const displayName = computed(() => {
  const r = resource.value;
  if (!r) return '';
  return String(r.name ?? r.title ?? '');
});

// A2（0605#2）：去掉与「共享与使用」字段重复的「基本信息」缩略块（提供方等已在决策块），
// 只把真正独有、轻量的事实（状态/最近更新/订阅量）收进 header 下一行细条，
// 首屏直达决策视图，消除「先缩略再详情」的跳跃感。
const headerFacts = computed(() => {
  const r = resource.value;
  if (!r) return [] as string[];
  const out: string[] = [];
  // status 已是后端下发的中文展示态（前端零词表，单一事实源），直接用、绝不裸出工程态（R12）。
  if (r.status) out.push(`状态 ${String(r.status)}`);
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
  if (loading.value) return '正在加载资源详情……';
  if (fetchError.value) return '暂时无法加载资源详情，请稍后再试。';
  if (resource.value) return resource.value.desc ? String(resource.value.desc) : '';
  return '未找到该资源';
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
        :title="DECISION_SECTION_TITLE"
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

      <!-- 字段清单 / 字段数据模型仅对库表资源渲染（T4）：文件 / 接口资源无字段模型概念，
           带 kind==='table' 门控消除文件类错显。 -->
      <section v-if="isTable && fields.length" class="detail-block">
        <h2 class="detail-block-title">{{ fields.length > 12 ? `字段清单（前 12 项，共 ${fields.length} 项）` : `字段清单（${fields.length} 项）` }}</h2>
        <ul class="chip-list">
          <li v-for="f in fields.slice(0, 12)" :key="f">{{ f }}</li>
        </ul>
      </section>
      <section v-if="canViewSchema" class="detail-block" data-testid="resource-schema-block">
        <!-- T1：默认折叠，点击才异步加载——消除与主详情竞速的二次撑高（对齐下方编目信息折叠块）。 -->
        <button
          type="button"
          class="collapse-toggle"
          :aria-expanded="showSchema"
          data-testid="resource-schema-toggle"
          @click="showSchema = !showSchema"
        >
          <span>字段数据模型</span>
          <span class="collapse-arrow">{{ showSchema ? '收起' : '展开' }}</span>
        </button>
        <template v-if="showSchema">
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
        </template>
      </section>
      <section v-if="explain.length" class="detail-block">
        <h2 class="detail-block-title">使用提示</h2>
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
