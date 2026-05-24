<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import { lookupResource, useSnapshot } from '@/composables/useSnapshot';
import { invokeActionStub } from '@/composables/useActionStub';
import DetailPanel from '@/components/DetailPanel.vue';

const route = useRoute();
const id = computed(() => String(route.params.id ?? ''));
const resource = lookupResource(id.value);
const { source } = useSnapshot();

const rows = computed(() => {
  const r = resource.value;
  if (!r) return [];
  const out: { label: string; value: string }[] = [];
  if (r.provider) out.push({ label: '提供方', value: String(r.provider) });
  if (r.zone) out.push({ label: '归属专题', value: String(r.zone) });
  if (r.status) out.push({ label: '当前状态', value: String(r.status) });
  if (r.updatedAt) out.push({ label: '最近更新', value: String(r.updatedAt) });
  if (r.subscribers !== undefined) out.push({ label: '订阅量', value: String(r.subscribers) });
  if (r.coverage) out.push({ label: '字段覆盖', value: String(r.coverage) });
  if (r.approvalRate) out.push({ label: '审批通过率', value: String(r.approvalRate) });
  return out;
});

const fields = computed(() => (Array.isArray(resource.value?.fields) ? (resource.value!.fields as string[]) : []));
const explain = computed(() => (Array.isArray(resource.value?.explain) ? (resource.value!.explain as string[]) : []));

async function apply() {
  await invokeActionStub({
    skillId: 'request.create',
    payload: { resource_id: id.value },
    successTitle: '复用申请已起草',
    pendingBackend: 'E2 申请管理 (e2/plan.yaml F4)',
  });
}
</script>

<template>
  <main class="page-shell">
    <nav class="crumbs"><a href="#/discovery">← 回到资源发现</a></nav>
    <header class="page-hero">
      <div class="page-kicker">P2 · 资源详情</div>
      <h1 v-if="resource" class="page-hero-title">{{ resource.name }}</h1>
      <h1 v-else class="page-hero-title">资源 <code>{{ id }}</code></h1>
      <p v-if="resource && resource.desc" class="page-hero-subtitle">{{ resource.desc }}</p>
      <p v-else-if="source !== 'live'" class="page-hero-subtitle">等待 /api/snapshot 装载该资源详情。</p>
      <p v-else class="page-hero-subtitle">未在当前 snapshot 中找到该资源；可能需要 F4 投影器派生扩展或回 P2 重新搜。</p>
    </header>

    <DetailPanel v-if="rows.length" title="基本信息" subtitle="来自 sd-default 真实资源" :rows="rows" />

    <section v-if="fields.length" class="panel">
      <header><h2 class="panel-title">字段清单（前 12 项）</h2></header>
      <ul class="chip-list">
        <li v-for="f in fields.slice(0, 12)" :key="f">{{ f }}</li>
      </ul>
    </section>

    <section v-if="explain.length" class="panel">
      <header><h2 class="panel-title">复用提示</h2></header>
      <ul class="hint-list">
        <li v-for="e in explain" :key="e">{{ e }}</li>
      </ul>
    </section>

    <section class="panel">
      <header><h2 class="panel-title">下一步</h2></header>
      <div class="actions">
        <button type="button" class="gov-btn gov-btn-primary" data-skill="request.create" @click="apply">发起复用申请</button>
        <a href="#/zones-pack" class="gov-btn gov-btn-secondary">看专题</a>
      </div>
    </section>
  </main>
</template>

<style scoped>
.page-shell { display: grid; gap: 16px; }
.crumbs a { font-size: 13px; color: var(--b-primary, #006be6); text-decoration: none; }
.crumbs a:hover { text-decoration: underline; }
.chip-list { list-style: none; padding: 0; margin: 12px 0 0; display: flex; flex-wrap: wrap; gap: 6px; }
.chip-list li { font-size: 12px; padding: 2px 10px; background: var(--b-bg-page, #f2f7fd); border: 1px solid var(--b-border, #d4e2f4); border-radius: 999px; }
.hint-list { padding-left: 20px; margin: 12px 0 0; font-size: 14px; }
.hint-list li { padding: 4px 0; }
.actions { display: flex; gap: 8px; margin-top: 12px; }
.gov-btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid transparent; text-decoration: none; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-secondary { background: #fff; border-color: var(--b-border, #d4e2f4); color: var(--b-neutral-text, #1a1d21); }
</style>
