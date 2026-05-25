<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import { useProvider, useSnapshot } from '@/composables/useSnapshot';
import { authFetch } from '@/composables/useAuth';
import { invokeActionStub, pushToast } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';
import { providerTodoCounts } from '@/lib/providerProjection';

const provider = useProvider();
const { source } = useSnapshot();
const publishWarnings = ref<Array<Record<string, unknown>>>([]);
const publishQueue = ref<Array<{ catalog_code: string; title: string }>>([]);
const publishQueueLoading = ref(false);

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

async function loadPublishQueue(): Promise<void> {
  if (source.value !== 'live') return;
  publishQueueLoading.value = true;
  try {
    const role = getProductRole().value;
    const resp = await authFetch('/api/skills/catalog.entry.query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ role, lifecycle_status: 'approved_pending_publish', limit: 5 }),
    });
    if (!resp.ok) {
      publishQueue.value = [];
      return;
    }
    const body = (await resp.json()) as { items?: Array<Record<string, unknown>> };
    publishQueue.value = (body.items ?? [])
      .map((item) => ({
        catalog_code: String(item.catalog_code ?? ''),
        title: String(item.title ?? item.catalog_code ?? '—'),
      }))
      .filter((item) => item.catalog_code);
  } finally {
    publishQueueLoading.value = false;
  }
}

watch(source, (live) => {
  if (live === 'live') void loadPublishQueue();
}, { immediate: true });

async function publishDraft(catalogCode: string) {
  const result = await invokeActionStub({
    skillId: 'catalog.entry.publish',
    payload: { catalog_code: catalogCode },
    successTitle: '目录已提交发布',
    refreshSnapshotAfter: true,
  });
  if (!result.ok) return;
  const root = (result.data ?? {}) as Record<string, unknown>;
  const inner = (root.result ?? root) as Record<string, unknown>;
  const warnings = (inner.duplicate_warnings ?? []) as Array<Record<string, unknown>>;
  publishWarnings.value = warnings;
  await loadPublishQueue();
  if (warnings.length) {
    pushToast({
      kind: 'warn',
      title: '发布成功 · 重复率提醒',
      detail: `检测到 ${warnings.length} 条可能重复（不阻断发布，请核对后再推广）`,
    });
  }
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
      <div v-if="source === 'live'" class="publish-section">
        <h3 class="section-title">待发布目录</h3>
        <p v-if="publishQueueLoading" class="focus-empty">正在加载待发布队列……</p>
        <p v-else-if="!publishQueue.length" class="focus-empty">暂无待发布目录（需先完成平台复核）</p>
        <div v-else class="row-actions">
          <button
            v-for="item in publishQueue"
            :key="item.catalog_code"
            type="button"
            class="gov-btn gov-btn-primary"
            data-testid="publish-catalog-btn"
            @click="publishDraft(item.catalog_code)"
          >
            发布「{{ item.title }}」
          </button>
        </div>
      </div>
      <div v-if="publishWarnings.length" class="warn-panel" data-testid="duplicate-warnings">
        <h3 class="warn-title">重复率提醒（{{ publishWarnings.length }} 条）</h3>
        <ul>
          <li v-for="(w, idx) in publishWarnings" :key="idx">
            {{ String(w.title ?? w.catalog_code ?? w.code ?? '—') }}
            <span v-if="w.similarity_score"> · 相似度 {{ w.similarity_score }}</span>
          </li>
        </ul>
      </div>
      <p v-else-if="source !== 'live'" class="focus-empty">等待数据装载……</p>
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
.publish-section { margin-top: 12px; }
.section-title { margin: 0 0 8px; font-size: 14px; font-weight: 600; }
.row-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.warn-panel { margin-top: 12px; padding: 10px 12px; border-radius: 6px; border: 1px solid #f0d080; background: #fff8e6; font-size: 13px; }
.warn-title { margin: 0 0 6px; font-size: 14px; color: #6b4e00; }
.warn-panel ul { margin: 0; padding-left: 18px; }
</style>
