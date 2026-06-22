<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailPanel from '@/components/DetailPanel.vue';
import DetailActions from '@/components/DetailActions.vue';
import { useProvider, useSnapshot } from '@/composables/useSnapshot';
import { invokeActionStub, pushToast } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';
import { canPerformAction } from '@/lib/pageAccess';
import { mapDetailRows } from '@/lib/detailDisplay';
import { displayRecordName } from '@/lib/userLanguage';
import {
  buildReverseDraftCreatePayload,
  buildReverseDraftSuggestPayload,
  mapReverseDraftCatalog,
  parseFieldSuggestions,
  parseTitleSuggestion,
  validateReverseDraftCatalog,
  type ReverseDraftCatalog,
  type ReverseFieldDecision,
} from '@/lib/reverseDraftPayload';

const route = useRoute();
const provider = useProvider();
const { source } = useSnapshot();
const role = getProductRole();
const selectedCatalogId = ref('');

const fieldCandidates = ref<ReverseFieldDecision[]>([]);
const suggestedTitle = ref('');
const suggesting = ref(false);
const suggestionEmpty = ref(false);

const SENSITIVE_LABEL: Record<string, string> = {
  '1': '1 级 · 公开',
  '2': '2 级 · 内部',
  '3': '3 级 · 敏感',
  '4': '4 级 · 高敏',
};

const canCreateDraft = computed(() =>
  canPerformAction('catalog.entry.reverse_draft.create', role.value),
);

const catalogs = computed(() => {
  const list = (provider.value.catalogs as unknown[] | undefined) ?? [];
  return list
    .map((c) => mapReverseDraftCatalog(c as Record<string, unknown>))
    .filter((c) => c.schema_ref.trim().length > 0);
});

function catalogIdFromRoute(): string {
  const raw = route.query.catalogId;
  return typeof raw === 'string' ? raw.trim() : '';
}

watch(catalogs, (list) => {
  const fromRoute = catalogIdFromRoute();
  if (fromRoute && list.some((c) => c.id === fromRoute)) {
    selectedCatalogId.value = fromRoute;
    return;
  }
  if (!selectedCatalogId.value && list.length) {
    selectedCatalogId.value = list[0].id;
  }
}, { immediate: true });

watch(() => route.query.catalogId, () => {
  const fromRoute = catalogIdFromRoute();
  if (fromRoute && catalogs.value.some((c) => c.id === fromRoute)) {
    selectedCatalogId.value = fromRoute;
  }
});

watch(selectedCatalogId, () => {
  fieldCandidates.value = [];
  suggestedTitle.value = '';
  suggestionEmpty.value = false;
});

const selected = computed(
  (): ReverseDraftCatalog | null =>
    catalogs.value.find((c) => c.id === selectedCatalogId.value) ?? null,
);

const previewRows = computed(() => {
  const c = selected.value;
  if (!c) return [];
  return mapDetailRows([
    { label: '目录名称', value: displayRecordName(c.name, c.catalog_code, '目录') },
    { label: '目录编码', value: c.catalog_code },
    { label: '当前状态', value: c.status || '—' },
    { label: '责任单位', value: c.owner || '—' },
    { label: '待补说明', value: c.issue || '暂无' },
  ]);
});

const headerMeta = computed(() => {
  if (source.value !== 'live') return '正在加载……';
  return catalogs.value.length ? `${catalogs.value.length} 个目录可发起反向编目` : '暂无目录数据';
});

function guardSelected(): ReverseDraftCatalog | null {
  const err = validateReverseDraftCatalog(selected.value);
  if (err) {
    pushToast({ kind: 'info', title: '暂无法操作', detail: err });
    return null;
  }
  return selected.value;
}

async function createDraft() {
  if (!canCreateDraft.value) {
    pushToast({
      kind: 'info',
      title: '暂无创建权限',
      detail: '创建反向编目草稿由部门操作员、部门管理员办理；草稿经部门管理员部门审、业务运营员平台审后发布。',
    });
    return;
  }
  const catalog = guardSelected();
  if (!catalog) return;
  const named: ReverseDraftCatalog =
    suggestedTitle.value.trim() && suggestedTitle.value.trim() !== catalog.name
      ? { ...catalog, name: suggestedTitle.value.trim() }
      : catalog;
  const res = await invokeActionStub({
    skillId: 'catalog.entry.reverse_draft.create',
    payload: buildReverseDraftCreatePayload(named, fieldCandidates.value),
    successTitle: '反向编目草稿已创建',
  });
  if (res.ok) {
    fieldCandidates.value = [];
  }
}

async function suggestFields() {
  const catalog = guardSelected();
  if (!catalog) return;
  suggesting.value = true;
  try {
    const res = await invokeActionStub({
      skillId: 'catalog.entry.reverse_draft.suggest',
      payload: buildReverseDraftSuggestPayload(catalog),
      suppressSuccessToast: true,
    });
    if (res.ok) {
      const suggestions = parseFieldSuggestions(res.data);
      fieldCandidates.value = suggestions.map((s) => ({
        field_en: s.field_en,
        field_cn: s.field_cn,
        sensitive_level: s.sensitive_level,
        source: s.source,
        selected: true,
      }));
      suggestedTitle.value = parseTitleSuggestion(res.data);
      suggestionEmpty.value = suggestions.length === 0;
      pushToast({
        kind: suggestions.length ? 'ok' : 'info',
        title: suggestions.length ? '字段建议已生成' : '暂无字段建议',
        detail: suggestions.length ? undefined : '该目录暂未匹配到可解析的 schema 字段，请换一个目录或补充元数据采集结果。',
      });
    }
  } finally {
    suggesting.value = false;
  }
}

const selectedCount = computed(() => fieldCandidates.value.filter((c) => c.selected).length);
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/provider/wizard/reverse-catalog">← 反向编目列表</a></nav>
    <section class="panel">
      <PageFocusHeader
        title="反向编目向导"
        :meta="headerMeta"
        :links="[{ label: '反向编目审核收件箱', href: '#/provider/inbox/field-decision' }]"
      />

      <template v-if="source === 'live' && catalogs.length">
        <label class="field-label">选择待编目目录</label>
        <select v-model="selectedCatalogId" class="gov-select">
          <option value="" disabled>请选择目录</option>
          <option v-for="c in catalogs" :key="c.id" :value="c.id">{{ displayRecordName(c.name, c.catalog_code, '目录') }}（{{ c.status }}）</option>
        </select>

        <DetailPanel v-if="selected" title="编目前预览" :rows="previewRows" />

        <p v-if="suggestionEmpty" class="focus-empty">该目录暂未匹配到可解析的字段建议。</p>

        <section v-if="fieldCandidates.length" class="field-candidates" data-testid="reverse-field-candidates">
          <header class="fc-head">
            <h3 class="fc-title">字段候选（{{ selectedCount }}/{{ fieldCandidates.length }} 项将入库）</h3>
            <p class="fc-sub">系统已解析 schema 给出字段名与敏感级建议，请逐项核对、修订并勾选后确认入库；敏感级由系统按 PII 规则预判，可调整。</p>
          </header>
          <label v-if="suggestedTitle" class="field-label">目录名称（建议，可改）</label>
          <input
            v-if="suggestedTitle"
            v-model="suggestedTitle"
            class="gov-input"
            data-testid="reverse-title-suggestion"
            placeholder="目录名称"
          />
          <table class="fc-table">
            <thead>
              <tr>
                <th class="fc-col-pick">入库</th>
                <th>字段（英文）</th>
                <th>中文名（可改）</th>
                <th>敏感级</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(c, i) in fieldCandidates" :key="c.field_en + i">
                <td class="fc-col-pick">
                  <input type="checkbox" v-model="c.selected" :data-testid="`fc-pick-${c.field_en}`" />
                </td>
                <td class="fc-en">{{ c.field_en }}</td>
                <td>
                  <input v-model="c.field_cn" class="gov-input fc-cn" :data-testid="`fc-cn-${c.field_en}`" />
                </td>
                <td>
                  <select v-model="c.sensitive_level" class="gov-select fc-level" :data-testid="`fc-level-${c.field_en}`">
                    <option v-for="lvl in ['1', '2', '3', '4']" :key="lvl" :value="lvl">{{ SENSITIVE_LABEL[lvl] }}</option>
                  </select>
                </td>
              </tr>
            </tbody>
          </table>
        </section>

        <DetailActions v-if="selected">
          <button
            type="button"
            class="gov-btn gov-btn-secondary"
            data-testid="reverse-suggest-btn"
            :disabled="suggesting"
            @click="suggestFields"
          >
            {{ suggesting ? '生成中…' : '生成字段建议' }}
          </button>
          <button v-if="canCreateDraft" type="button" class="gov-btn gov-btn-primary" @click="createDraft">
            创建反向编目草稿
          </button>
        </DetailActions>
      </template>

      <p v-else-if="source === 'live'" class="focus-empty">当前快照中暂无目录条目，待提供方数据同步后可在此发起反向编目。</p>
      <p v-else class="focus-empty">等待数据装载……</p>
    </section>
  </main>
</template>

<style scoped>
.crumbs { margin-bottom: 4px; }
.crumbs a { font-size: 13px; color: var(--b-primary, #006be6); text-decoration: none; }
.crumbs a:hover { text-decoration: underline; }
.field-label { display: block; font-size: 13px; color: var(--b-muted, #5c6370); margin: 8px 0 6px; }
.gov-select { width: 100%; max-width: 420px; padding: 8px 10px; border: 1px solid var(--b-border, #d4e2f4); border-radius: 6px; font-size: 14px; margin-bottom: 12px; }
.gov-input { width: 100%; max-width: 420px; padding: 8px 10px; border: 1px solid var(--b-border, #d4e2f4); border-radius: 6px; font-size: 14px; margin-bottom: 12px; }
.gov-btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid transparent; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-secondary { background: #fff; border-color: var(--b-border, #d4e2f4); }
.gov-btn:disabled { opacity: 0.6; cursor: not-allowed; }
.field-candidates { margin: 14px 0; }
.fc-head { margin-bottom: 8px; }
.fc-title { font-size: 14px; font-weight: 600; color: var(--b-neutral-text, #1a1d21); margin: 0 0 4px; }
.fc-sub { font-size: 12px; color: var(--b-muted, #5c6370); margin: 0 0 8px; }
.fc-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.fc-table th, .fc-table td { text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--b-border, #e6eef8); }
.fc-table th { font-size: 12px; color: var(--b-muted, #5c6370); font-weight: 600; }
.fc-col-pick { width: 48px; text-align: center; }
.fc-en { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color: var(--b-neutral-text, #1a1d21); }
.fc-cn { max-width: 220px; margin-bottom: 0; }
.fc-level { max-width: 160px; margin-bottom: 0; }
</style>
