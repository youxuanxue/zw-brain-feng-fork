<script setup lang="ts">
import { computed, ref } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailPanel from '@/components/DetailPanel.vue';
import DetailActions from '@/components/DetailActions.vue';
import { useProvider, useSnapshot } from '@/composables/useSnapshot';
import { invokeActionStub } from '@/composables/useActionStub';
import { mapDetailRows } from '@/lib/detailDisplay';
import { buildQualityRuleUpsertPayload, mapProviderCatalog } from '@/lib/providerActionPayload';

const provider = useProvider();
const { source } = useSnapshot();
const selectedId = ref('');

const catalogs = computed(() => {
  const list = (provider.value.catalogs as unknown[] | undefined) ?? [];
  return list.map((c) => mapProviderCatalog(c as Record<string, unknown>));
});

const selected = computed(
  () =>
    catalogs.value.find((c) => c.id === selectedId.value) ??
    catalogs.value.find((c) => (c.status ?? '').includes('待')) ??
    null,
);

const previewRows = computed(() => {
  const c = selected.value;
  if (!c) return [];
  return mapDetailRows([
    { label: '目录名称', value: c.name },
    { label: '质检状态', value: c.status || '—' },
    { label: '待补说明', value: c.issue || '暂无' },
  ]);
});

const headerMeta = computed(() => {
  if (source.value !== 'live') return '正在加载……';
  const pending = catalogs.value.filter((c) => (c.status ?? '').includes('待')).length;
  return pending
    ? `${pending} 个目录待质检 · 共 ${catalogs.value.length} 个`
    : `${catalogs.value.length} 个目录均已通过质检`;
});

async function upsertRule() {
  if (!selected.value) return;
  await invokeActionStub({
    skillId: 'quality.rule.upsert',
    payload: buildQualityRuleUpsertPayload(selected.value),
    successTitle: '质量规则已保存',
  });
}
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/provider">← 提供方管理</a></nav>
    <section class="panel">
      <PageFocusHeader
        title="质量规则向导"
        :meta="headerMeta"
        :links="[{ label: '反向编目向导', href: '#/provider/wizard/reverse-catalog' }]"
      />

      <template v-if="source === 'live' && catalogs.length">
        <label class="field-label">选择待配置目录</label>
        <select v-model="selectedId" class="gov-select">
          <option value="" disabled>请选择目录</option>
          <option v-for="c in catalogs" :key="c.id" :value="c.id">{{ c.name }}（{{ c.status }}）</option>
        </select>
        <DetailPanel title="规则预览" :rows="previewRows" />
        <DetailActions>
          <button type="button" class="gov-btn gov-btn-primary" @click="upsertRule">保存质量规则</button>
        </DetailActions>
      </template>
      <p v-else-if="source === 'live'" class="focus-empty">暂无目录数据。</p>
      <p v-else class="focus-empty">等待数据装载……</p>
    </section>
  </main>
</template>

<style scoped>
.field-label { display: block; font-size: 13px; margin-bottom: 6px; color: var(--b-muted, #5c6370); }
.gov-select { width: 100%; max-width: 480px; padding: 6px 10px; margin-bottom: 12px; border-radius: 6px; border: 1px solid var(--b-border, #d4e2f4); }
.gov-btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid transparent; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
</style>
