<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailPanel from '@/components/DetailPanel.vue';
import DetailActions from '@/components/DetailActions.vue';
import { useProvider, useSnapshot } from '@/composables/useSnapshot';
import { invokeActionStub, pushToast } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';
import { mapDetailRows } from '@/lib/detailDisplay';
import {
  buildReverseDraftCreatePayload,
  buildReverseDraftSuggestPayload,
  mapReverseDraftCatalog,
  validateReverseDraftCatalog,
  type ReverseDraftCatalog,
} from '@/lib/reverseDraftPayload';

const provider = useProvider();
const { source } = useSnapshot();
const role = getProductRole();
const selectedCatalogId = ref('');

// 操作员 + 管理员均可发起反向编目草稿（v5 旧平台口径，permission-realignment）
const canCreateDraft = computed(() =>
  role.value === 'ROLE_ORGAN_OPERATER' || role.value === 'ROLE_ORGAN_MANAGER',
);

const catalogs = computed(() => {
  const list = (provider.value.catalogs as unknown[] | undefined) ?? [];
  return list.map((c) => mapReverseDraftCatalog(c as Record<string, unknown>));
});

watch(catalogs, (list) => {
  if (!selectedCatalogId.value && list.length) {
    selectedCatalogId.value = list[0].id;
  }
}, { immediate: true });

const selected = computed(
  (): ReverseDraftCatalog | null =>
    catalogs.value.find((c) => c.id === selectedCatalogId.value) ?? null,
);

const previewRows = computed(() => {
  const c = selected.value;
  if (!c) return [];
  return mapDetailRows([
    { label: '目录名称', value: c.name },
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
      detail: '创建反向编目草稿由部门管理员办理；业务运营员请在反向编目审核收件箱审核草稿。',
    });
    return;
  }
  const catalog = guardSelected();
  if (!catalog) return;
  await invokeActionStub({
    skillId: 'catalog.entry.reverse_draft.create',
    payload: buildReverseDraftCreatePayload(catalog),
    successTitle: '反向编目草稿已创建',
  });
}

async function suggestFields() {
  const catalog = guardSelected();
  if (!catalog) return;
  await invokeActionStub({
    skillId: 'catalog.entry.reverse_draft.suggest',
    payload: buildReverseDraftSuggestPayload(catalog),
    successTitle: '字段建议已生成',
  });
}
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
          <option v-for="c in catalogs" :key="c.id" :value="c.id">{{ c.name }}（{{ c.status }}）</option>
        </select>

        <DetailPanel v-if="selected" title="编目前预览" :rows="previewRows" />

        <p v-if="selected && !canCreateDraft" class="role-hint">
          业务运营员可生成字段建议；创建草稿请切换为部门管理员，或到
          <a href="#/provider/inbox/field-decision">反向编目审核收件箱</a> 审核已有草稿。
        </p>

        <DetailActions v-if="selected">
          <button type="button" class="gov-btn gov-btn-secondary" @click="suggestFields">生成字段建议</button>
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
.gov-btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid transparent; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-secondary { background: #fff; border-color: var(--b-border, #d4e2f4); }
.role-hint { font-size: 13px; color: var(--b-muted, #5c6370); margin: 0 0 12px; line-height: 1.5; }
.role-hint a { color: var(--b-primary, #006be6); }
</style>
