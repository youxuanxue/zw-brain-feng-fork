<script setup lang="ts">
import { computed } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import { useProvider, useSnapshot } from '@/composables/useSnapshot';
import { invokeActionStub } from '@/composables/useActionStub';
import { providerTodoCounts } from '@/lib/providerProjection';

const provider = useProvider();
const { source } = useSnapshot();

const counts = computed(() => providerTodoCounts(provider.value as Record<string, unknown>));

const headerMeta = computed(() => {
  if (source.value !== 'live') return '正在加载……';
  const c = counts.value;
  return `待办：字段裁决 ${c.fieldDec} · 挂接审核 ${c.hookup} · 供需 ${c.demand} · 异议 ${c.objection}`;
});

const statCards = computed(() => {
  const c = counts.value;
  return [
    { key: 'field-decision', label: '字段裁决', value: c.fieldDec, href: '#/provider/inbox/field-decision' },
    { key: 'hookup-review', label: '挂接审核', value: c.hookup, href: '#/provider/inbox/hookup-review' },
    { key: 'demand-match', label: '供需对接', value: c.demand, href: '#/provider/inbox/demand-match' },
    { key: 'objection', label: '异议响应', value: c.objection, href: '#/provider/inbox/objection' },
  ];
});

async function publishDraft(catalogCode: string) {
  await invokeActionStub({
    skillId: 'catalog.entry.publish',
    payload: { catalog_code: catalogCode },
    successTitle: '已提交发布审核',
  });
}
</script>

<template>
  <main class="focus-page">
    <section class="panel">
      <PageFocusHeader
        title="提供方管理"
        :meta="headerMeta"
        :links="[
          { label: '反向编目', href: '#/provider/wizard/reverse-catalog' },
          { label: 'API 服务化', href: '#/provider/wizard/api-service' },
          { label: '质量规则', href: '#/provider/wizard/quality-rule' },
        ]"
      />

      <div v-if="source === 'live'" class="stat-grid">
        <a v-for="c in statCards" :key="c.key" :href="c.href" class="stat-card">
          <strong>{{ c.value }}</strong>
          <em>{{ c.label }}</em>
        </a>
      </div>
      <div v-if="source === 'live'" class="row-actions" style="margin-top: 12px">
        <button type="button" class="gov-btn gov-btn-primary" @click="publishDraft('cat-parking')">
          提交草稿到发布审核（示例）
        </button>
      </div>
      <p v-else class="focus-empty">等待数据装载……</p>
    </section>
  </main>
</template>

<style scoped>
.stat-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 10px; margin-top: 8px; }
.stat-card { display: grid; gap: 4px; padding: 14px; border: 1px solid var(--b-border, #d4e2f4); border-radius: 8px; text-decoration: none; color: inherit; background: #fff; }
.stat-card strong { font-size: 22px; color: var(--b-primary, #006be6); }
.stat-card em { font-style: normal; font-size: 13px; color: var(--b-muted, #5c6370); }
.gov-btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid transparent; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
</style>
