<script setup lang="ts">
import { computed } from 'vue';
import { useZones, useSnapshot } from '@/composables/useSnapshot';
import { invokeActionStub } from '@/composables/useActionStub';
import DrillStrip from '@/components/DrillStrip.vue';

const zones = useZones();
const { source } = useSnapshot();
const items = computed(() =>
  zones.value.map((z) => {
    const it = z as Record<string, unknown>;
    return {
      id: String(it.id ?? ''),
      name: String(it.name ?? ''),
      desc: String(it.desc ?? it.description ?? ''),
      status: String(it.status ?? ''),
      assets: Array.isArray(it.assets) ? (it.assets as string[]) : [],
    };
  })
);
const drillItems = computed(() => [
  { label: '回到 P2', href: '#/discovery', hint: '从资源找' },
  { label: '看在途申请', href: '#/request-flow', hint: '复用进度' },
]);

async function subscribe(id: string) {
  await invokeActionStub({
    skillId: 'zone.publish_topic_projection',
    payload: { zone_id: id },
    successTitle: '已加入订阅候选',
    pendingBackend: 'E3 专题运营 (e3/plan.yaml F6)',
  });
}
</script>

<template>
  <main class="page-shell">
    <header class="page-hero">
      <div class="page-kicker">P7 · J1 + J2</div>
      <h1 class="page-hero-title">共享专区 · 专题包</h1>
      <p class="page-hero-subtitle">主题化聚合与订阅入口（业务方反馈从「几乎不用」回归「必保留」）。</p>
    </header>

    <DrillStrip kicker="跨页跳转" :items="drillItems" />

    <section class="panel">
      <header>
        <h2 class="panel-title">专题包列表</h2>
        <p class="panel-subtitle">F3 阶段：卡片 + 资产清单 + 订阅 stub</p>
      </header>
      <div v-if="source === 'live' && items.length">
        <div class="zone-grid">
          <article v-for="z in items" :key="z.id" class="zone-card">
            <header>
              <a :href="`#/zones-pack/zone/${encodeURIComponent(z.id)}`" class="zone-title"><strong>{{ z.name || z.id }}</strong></a>
              <span v-if="z.status" class="zone-status">{{ z.status }}</span>
            </header>
            <p v-if="z.desc" class="zone-desc">{{ z.desc }}</p>
            <ul v-if="z.assets.length" class="zone-assets">
              <li v-for="a in z.assets.slice(0, 5)" :key="a">{{ a }}</li>
            </ul>
            <footer>
              <button type="button" class="gov-btn gov-btn-primary" data-skill="zone.publish_topic_projection" @click="subscribe(z.id)">订阅专题</button>
              <a :href="`#/zones-pack/zone/${encodeURIComponent(z.id)}`" class="gov-btn gov-btn-secondary">查看详情</a>
            </footer>
          </article>
        </div>
      </div>
      <div v-else-if="source === 'live'" class="text-body text-zw-mute">暂无专题包。</div>
      <div v-else class="text-body text-zw-mute">等待 /api/snapshot 装载专题包列表。</div>
    </section>
  </main>
</template>

<style scoped>
.page-shell { display: grid; gap: 16px; }
.zone-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; margin-top: 12px; }
.zone-card { border: 1px solid var(--b-border, #d4e2f4); border-radius: 10px; padding: 16px; background: #fff; display: grid; gap: 8px; }
.zone-card header { display: flex; align-items: center; gap: 8px; }
.zone-title { text-decoration: none; color: inherit; }
.zone-status { font-size: 12px; padding: 2px 8px; border-radius: 999px; background: var(--b-bg-subtle, #e8f2fc); color: var(--b-primary, #006be6); }
.zone-desc { font-size: 13px; color: var(--b-muted, #5c6370); margin: 0; }
.zone-assets { list-style: none; padding: 0; margin: 0; display: flex; flex-wrap: wrap; gap: 6px; }
.zone-assets li { font-size: 12px; padding: 2px 8px; border-radius: 4px; background: var(--b-bg-page, #f2f7fd); border: 1px solid var(--b-border, #d4e2f4); }
.zone-card footer { display: flex; gap: 8px; }
.gov-btn { padding: 4px 12px; border-radius: 6px; font-size: 12px; cursor: pointer; border: 1px solid transparent; text-decoration: none; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-secondary { background: #fff; border-color: var(--b-border, #d4e2f4); color: var(--b-neutral-text, #1a1d21); }
</style>
