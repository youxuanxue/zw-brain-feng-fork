<script setup lang="ts">
import { computed, ref, watch } from 'vue';
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

const provider = useProvider();
const { source } = useSnapshot();
const role = getProductRole();
const selectedCatalogId = ref('');

// 反向编目字段候选：suggest 后端解析 schema 给出（含 PII 定密 sensitive_level），
// 在此渲染成可勾选/可改的候选表，确认后随 create 一并入库（j2-online-catalog-compile.feature:33-35
// 「修订→确认入库」）。每次切目录或重新 suggest 时清空，避免跨目录串候选。
const fieldCandidates = ref<ReverseFieldDecision[]>([]);
const suggestedTitle = ref('');
const suggesting = ref(false);

const SENSITIVE_LABEL: Record<string, string> = {
  '1': '1 级 · 公开',
  '2': '2 级 · 内部',
  '3': '3 级 · 敏感',
  '4': '4 级 · 高敏',
};

// 操作员 + 管理员均可发起反向编目草稿（v5 旧平台口径，permission-realignment）
// R-014：走 canPerformAction chokepoint（catalog.entry.reverse_draft.create gate），
// 不在 page 内硬编码 role 比对；与后端 policy set-equal。
const canCreateDraft = computed(() =>
  canPerformAction('catalog.entry.reverse_draft.create', role.value),
);

const catalogs = computed(() => {
  const list = (provider.value.catalogs as unknown[] | undefined) ?? [];
  return list
    .map((c) => mapReverseDraftCatalog(c as Record<string, unknown>))
    // 只列可发起的（有 schema 引用）：缺 schema_ref 的行（如新编草稿）选中也只会被
    // validate 拦下，列出来即虚数（headerMeta 计数夸大）——无法操作 = 不出现。
    .filter((c) => c.schema_ref.trim().length > 0);
});

watch(catalogs, (list) => {
  if (!selectedCatalogId.value && list.length) {
    selectedCatalogId.value = list[0].id;
  }
}, { immediate: true });

// 切换目录即清空上一目录的候选/标题，候选只对当前选中目录有效。
watch(selectedCatalogId, () => {
  fieldCandidates.value = [];
  suggestedTitle.value = '';
});

const selected = computed(
  (): ReverseDraftCatalog | null =>
    catalogs.value.find((c) => c.id === selectedCatalogId.value) ?? null,
);

const previewRows = computed(() => {
  const c = selected.value;
  if (!c) return [];
  return mapDetailRows([
    // 名==编码 / 名是裸编码 → 「未命名目录（编码 …）」，不把目录码当名直出（R12）。
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
  // 用户可在候选表里把标题改进到草稿名（suggest 给的 title_suggestion 已回填到此处）。
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
    // 入库成功即清空候选，避免对同一目录重复创建时串入旧候选。
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
      successTitle: '字段建议已生成',
    });
    if (res.ok) {
      // 接住 res.data：把后端三档建议渲染成可勾选/可改的候选表（默认全选）。
      fieldCandidates.value = parseFieldSuggestions(res.data).map((s) => ({
        field_en: s.field_en,
        field_cn: s.field_cn,
        sensitive_level: s.sensitive_level,
        source: s.source,
        selected: true,
      }));
      suggestedTitle.value = parseTitleSuggestion(res.data);
    }
  } finally {
    suggesting.value = false;
  }
}

const selectedCount = computed(() => fieldCandidates.value.filter((c) => c.selected).length);
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/provider">← 提供方管理</a></nav>
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
