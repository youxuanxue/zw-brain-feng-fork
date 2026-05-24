<script setup lang="ts">
import { computed, ref } from 'vue';
import { useDiscoveryResources, useSnapshot } from '@/composables/useSnapshot';
import { invokeActionStub, pushToast } from '@/composables/useActionStub';
import ResourceCard from '@/components/ResourceCard.vue';
import DrillStrip from '@/components/DrillStrip.vue';
import NLAcceleratorPanel from '@/components/NLAcceleratorPanel.vue';
import type { StructuredAction } from '@/composables/useNLAccelerator';

const NL_PRESETS_P2 = [
  '查省营商环境相关数据',
  '近 7 天高使用资源',
  '关联水电气交叉数据',
];

function consumeNLAction(action: StructuredAction) {
  // navigate kind 由 NLAcceleratorPanel 自身处理（window.location.hash）。
  if (action.kind === 'filter' && action.payload && typeof action.payload.zone === 'string') {
    query.value = String(action.payload.zone);
  } else if (action.kind === 'invoke' && action.target) {
    void invokeActionStub({ skillId: action.target, payload: action.payload, successTitle: action.label });
  } else if (action.kind === 'filter' || action.kind === 'draft') {
    pushToast({ kind: 'info', title: '已应用', detail: action.label });
  }
}

const resources = useDiscoveryResources();
const { source } = useSnapshot();
const query = ref<string>('');

const filtered = computed(() => {
  const q = query.value.trim();
  if (!q) return resources.value;
  return resources.value.filter((r) => {
    const it = r as Record<string, unknown>;
    return JSON.stringify(it).includes(q);
  });
});

const drillItems = computed(() => [
  { label: '高频复用', href: '#/discovery', hint: '按订阅量排序' },
  { label: '专题入口', href: '#/zones-pack', hint: '从场景找资源' },
  { label: '我的申请', href: '#/request-flow', hint: '看在途进度' },
]);

async function applyTo(id: string) {
  await invokeActionStub({
    skillId: 'request.create',
    payload: { resource_id: id, purpose: '示例：来自 P2 发现页一键发起' },
    successTitle: '复用申请已起草',
    pendingBackend: 'E2 申请管理 handler (e2/plan.yaml F4)',
  });
}
</script>

<template>
  <main class="page-shell">
    <header class="page-hero">
      <div class="hero-row">
        <div>
          <div class="page-kicker">P2 · J1 找数→用数</div>
          <h1 class="page-hero-title">资源发现</h1>
          <p class="page-hero-subtitle">输入业务说法即可命中已有资源；先复用模板，再补差异字段。</p>
        </div>
        <NLAcceleratorPanel page-anchor="P2" :presets="NL_PRESETS_P2" @action="consumeNLAction" />
      </div>
      <form class="page-toolbar" role="search" @submit.prevent>
        <label class="sr-only" for="p2-search">搜索资源</label>
        <input
          id="p2-search"
          v-model="query"
          type="search"
          class="field-input"
          placeholder="例如：停车场信息 / 营商环境 / 一表通"
          autocomplete="off"
        />
      </form>
    </header>

    <DrillStrip kicker="按场景或意图直达" :items="drillItems" />

    <section class="panel">
      <header>
        <h2 class="panel-title">可复用资源</h2>
        <p class="panel-subtitle">来自 sd-default 单租户单省（山东省）</p>
      </header>
      <div v-if="source === 'live' && filtered.length">
        <div class="card-grid">
          <ResourceCard v-for="r in filtered" :key="String((r as Record<string, unknown>).id ?? '')" :resource="(r as Record<string, unknown>)" show-action @apply="applyTo" />
        </div>
      </div>
      <div v-else-if="source === 'live'" class="text-body text-zw-mute">未命中。可尝试更宽的关键词。</div>
      <div v-else class="text-body text-zw-mute">等待 /api/snapshot 装载真实资源后渲染。</div>
    </section>
  </main>
</template>

<style scoped>
.page-shell { display: grid; gap: 16px; }
.hero-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.page-toolbar { margin-top: 12px; }
.field-input { width: 100%; max-width: 480px; padding: 8px 12px; border: 1px solid var(--b-border, #d4e2f4); border-radius: 6px; font-size: 14px; }
.card-grid { display: grid; gap: 12px; margin-top: 12px; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
</style>
