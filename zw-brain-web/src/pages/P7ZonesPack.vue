<script setup lang="ts">
import { computed } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import { useZones, useSnapshot } from '@/composables/useSnapshot';
import { invokeActionStub } from '@/composables/useActionStub';

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

const headerMeta = computed(() => {
  if (source.value !== 'live') return '正在加载……';
  return items.value.length ? `${items.value.length} 个专题可订阅` : '暂无专题包';
});

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
  <main class="focus-page">
    <section class="panel">
      <PageFocusHeader
        title="共享专题包"
        :meta="headerMeta"
        :links="[
          { label: '资源发现', href: '#/discovery' },
          { label: '申请进度', href: '#/request-flow' },
        ]"
      />

      <div v-if="source === 'live' && items.length" class="zone-grid">
        <article v-for="z in items" :key="z.id" class="zone-card">
          <header>
            <a :href="`#/zones-pack/zone/${encodeURIComponent(z.id)}`" class="zone-title"><strong>{{ z.name || z.id }}</strong></a>
            <span v-if="z.status" class="zone-status">{{ z.status }}</span>
          </header>
          <p v-if="z.desc" class="zone-desc">{{ z.desc }}</p>
          <footer class="row-actions">
            <button type="button" class="gov-btn gov-btn-primary" @click="subscribe(z.id)">订阅专题</button>
            <a :href="`#/zones-pack/zone/${encodeURIComponent(z.id)}`" class="gov-btn gov-btn-secondary">详情</a>
          </footer>
        </article>
      </div>
      <p v-else-if="source === 'live'" class="focus-empty">暂无专题包。</p>
      <p v-else class="focus-empty">等待数据装载……</p>
    </section>
  </main>
</template>

<style scoped>
.zone-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; margin-top: 8px; }
.zone-card { border: 1px solid var(--b-border, #d4e2f4); border-radius: 10px; padding: 14px; background: #fff; display: grid; gap: 8px; }
.zone-card header { display: flex; align-items: center; gap: 8px; }
.zone-title { text-decoration: none; color: inherit; }
.zone-status { font-size: 12px; padding: 2px 8px; border-radius: 999px; background: var(--b-bg-subtle, #e8f2fc); color: var(--b-primary, #006be6); }
.zone-desc { font-size: 13px; color: var(--b-muted, #5c6370); margin: 0; }
.gov-btn { padding: 4px 12px; border-radius: 6px; font-size: 12px; cursor: pointer; border: 1px solid transparent; text-decoration: none; display: inline-flex; align-items: center; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-secondary { background: #fff; border-color: var(--b-border, #d4e2f4); }
</style>
