<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailPanel from '@/components/DetailPanel.vue';
import DetailActions from '@/components/DetailActions.vue';
import { useSnapshot, useZones } from '@/composables/useSnapshot';
import { invokeActionStub } from '@/composables/useActionStub';
import { mapDetailRows } from '@/lib/detailDisplay';
import { formatTodoStatus, todoStatusTone } from '@/lib/statusLabels';

const route = useRoute();
const id = computed(() => String(route.params.id ?? ''));
const zones = useZones();
const zone = computed(() => {
  const target = id.value;
  return (
    zones.value.find((z) => String((z as Record<string, unknown>).id ?? '') === target) as
      | Record<string, unknown>
      | undefined
  );
});
const { source } = useSnapshot();

const rows = computed(() => {
  const z = zone.value;
  if (!z) return mapDetailRows([{ label: '专题编号', value: id.value }]);
  return mapDetailRows([
    { label: '专题编号', value: id.value },
    { label: '专题名称', value: String(z.name ?? '—') },
    { label: '上线状态', value: formatTodoStatus(String(z.status ?? '')) },
    { label: '订阅量', value: z.subscribers !== undefined ? String(z.subscribers) : '—' },
  ]);
});

const assets = computed(() => (Array.isArray(zone.value?.assets) ? (zone.value!.assets as string[]) : []));
const nextActions = computed(() =>
  Array.isArray(zone.value?.nextActions) ? (zone.value!.nextActions as string[]) : []
);
const trust = computed(() => (Array.isArray(zone.value?.trust) ? (zone.value!.trust as string[]) : []));
const aiGuide = computed(() => String(zone.value?.aiGuide ?? zone.value?.desc ?? ''));

const headerTitle = computed(() => {
  if (zone.value?.name) return String(zone.value.name);
  if (source.value === 'live') return id.value;
  return '正在加载……';
});

const headerMeta = computed(() => {
  if (zone.value?.desc) return String(zone.value.desc);
  if (source.value === 'live' && !zone.value) return '未找到该专题';
  if (source.value !== 'live') return '正在加载专题详情……';
  return '';
});

const statusTone = computed(() => todoStatusTone(String(zone.value?.status ?? '')));

const packageCode = computed(() => String(zone.value?.package_code ?? zone.value?.id ?? id.value));

async function subscribe() {
  await invokeActionStub({
    skillId: 'topic.package.subscribe',
    payload: { package_code: packageCode.value },
    successTitle: '已订阅专题',
  });
}
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/zones-pack">← 共享专题包</a></nav>
    <section class="panel">
      <PageFocusHeader :title="headerTitle" :meta="headerMeta">
        <template v-if="zone?.status" #aside>
          <span class="zone-badge" :class="statusTone">{{ formatTodoStatus(String(zone.status)) }}</span>
        </template>
      </PageFocusHeader>

      <DetailPanel v-if="rows.length" title="基本信息" :rows="rows" />

      <section v-if="aiGuide" class="detail-block">
        <h2 class="detail-block-title">专题指引</h2>
        <p class="guide-text">{{ aiGuide }}</p>
      </section>

      <section v-if="assets.length" class="detail-block">
        <h2 class="detail-block-title">包含资产</h2>
        <ul class="asset-list">
          <li v-for="a in assets" :key="a">{{ a }}</li>
        </ul>
      </section>

      <section v-if="nextActions.length" class="detail-block">
        <h2 class="detail-block-title">推荐下一步</h2>
        <ul class="hint-list">
          <li v-for="n in nextActions" :key="n">{{ n }}</li>
        </ul>
      </section>

      <section v-if="trust.length" class="detail-block">
        <h2 class="detail-block-title">可信说明</h2>
        <ul class="hint-list">
          <li v-for="t in trust" :key="t">{{ t }}</li>
        </ul>
      </section>

      <DetailActions v-if="zone">
        <button type="button" class="gov-btn gov-btn-primary" @click="subscribe">订阅专题</button>
        <a href="#/discovery" class="gov-btn gov-btn-secondary">去发现资源</a>
      </DetailActions>
    </section>
  </main>
</template>

<style scoped>
.zone-badge { font-size: 12px; padding: 4px 10px; border-radius: 999px; }
.tone-ok { background: #f6ffed; color: #389e0d; }
.tone-warn { background: #fff7e6; color: #ad6800; }
.tone-neutral { background: var(--b-bg-subtle, #e8f2fc); color: var(--b-muted, #5c6370); }
.guide-text { margin: 8px 0 0; font-size: 14px; line-height: 1.6; color: var(--b-text, #1a1d21); }
.asset-list { list-style: disc; padding-left: 20px; margin: 8px 0 0; font-size: 14px; line-height: 1.6; }
.hint-list { padding-left: 20px; margin: 8px 0 0; font-size: 14px; line-height: 1.6; }
.gov-btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid transparent; text-decoration: none; display: inline-flex; align-items: center; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-secondary { background: #fff; border-color: var(--b-border, #d4e2f4); }
</style>
