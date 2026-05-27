<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import { useProvider, useSnapshot } from '@/composables/useSnapshot';
import { authFetch } from '@/composables/useAuth';
import { invokeActionStub, pushToast } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';
import { providerTodoCounts } from '@/lib/providerProjection';
import { canPerformAction, filterByRouteAccess } from '@/lib/pageAccess';

const provider = useProvider();
const { source } = useSnapshot();
const role = getProductRole();
const publishWarnings = ref<Array<Record<string, unknown>>>([]);
const publishQueue = ref<Array<{ catalog_code: string; title: string }>>([]);
const publishQueueLoading = ref(false);

const counts = computed(() => providerTodoCounts(provider.value as Record<string, unknown>));

const statCards = computed(() => {
  const c = counts.value;
  return [
    { key: 'field-decision', label: '字段裁决', value: c.fieldDec, href: '#/provider/inbox/field-decision' },
    { key: 'hookup-review', label: '挂接审核', value: c.hookup, href: '#/provider/inbox/hookup-review' },
    { key: 'demand-match', label: '供需对接', value: c.demand, href: '#/provider/inbox/demand-match' },
    { key: 'objection', label: '异议响应', value: c.objection, href: '#/provider/inbox/objection' },
  ];
});

// 按当前 role 过滤待办卡：OPERATER 见不到 field-decision/hookup-review/objection（无权进），
// 同 PageFocusHeader 单点过滤；headerMeta 跟随 visibleStatCards，无卡时给本岗位的引导语。
const visibleStatCards = computed(() =>
  filterByRouteAccess(statCards.value, (c) => c.href, role.value),
);

const canPublishCatalog = computed(() => canPerformAction('catalog.entry.publish', role.value));

const headerMeta = computed(() => {
  if (source.value !== 'live') return '正在加载……';
  const visible = visibleStatCards.value;
  if (!visible.length) return '本岗位无待办（可通过顶栏入口创建/查看自己的目录）';
  return '待办：' + visible.map((c) => `${c.label} ${c.value}`).join(' · ');
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
          { label: '在线编制', href: '#/provider/wizard/inline-catalog' },
          { label: '目录审核', href: '#/provider/inbox/catalog-review' },
          { label: '反向编目', href: '#/provider/wizard/reverse-catalog' },
          { label: 'API 服务化', href: '#/provider/wizard/api-service' },
          {
            label: '资源挂接（Wave-1 ⏳）',
            href: '#',
            disabledReason:
              '为已发布目录补挂 table / file 物化资源 的提交侧 wizard 待立项；当前 OPERATER 只能挂 api（走「API 服务化」入口）。详见 docs/preflight-debt.md 2026-05-27 J2-4 条目。',
          },
          { label: '质量规则', href: '#/provider/wizard/quality-rule' },
        ]"
      />

      <div v-if="source === 'live' && visibleStatCards.length" class="stat-grid">
        <a v-for="c in visibleStatCards" :key="c.key" :href="c.href" class="stat-card">
          <strong>{{ c.value }}</strong>
          <em>{{ c.label }}</em>
        </a>
      </div>
      <section v-if="source === 'live' && canPublishCatalog" class="publish-card" aria-label="待发布目录">
        <header class="publish-card-head">
          <h3 class="section-title">待发布目录</h3>
          <span v-if="publishQueue.length" class="publish-count">{{ publishQueue.length }} 项</span>
        </header>
        <p v-if="publishQueueLoading" class="focus-empty">正在加载待发布队列……</p>
        <p v-else-if="!publishQueue.length" class="focus-empty">暂无待发布目录（需先完成平台复核）</p>
        <ul v-else class="publish-list">
          <li v-for="item in publishQueue" :key="item.catalog_code" class="publish-row">
            <div class="publish-row-meta">
              <span class="publish-row-title" :title="item.title">{{ item.title }}</span>
              <code class="publish-row-code" :title="item.catalog_code">{{ item.catalog_code }}</code>
            </div>
            <button
              type="button"
              class="gov-btn gov-btn-primary publish-row-btn"
              data-testid="publish-catalog-btn"
              @click="publishDraft(item.catalog_code)"
            >发布</button>
          </li>
        </ul>
        <div v-if="publishWarnings.length" class="warn-panel" data-testid="duplicate-warnings">
          <h4 class="warn-title">重复率提醒 · {{ publishWarnings.length }} 条</h4>
          <ul>
            <li v-for="(w, idx) in publishWarnings" :key="idx">
              {{ String(w.title ?? w.catalog_code ?? w.code ?? '—') }}
              <span v-if="w.similarity_score"> · 相似度 {{ w.similarity_score }}</span>
            </li>
          </ul>
        </div>
      </section>
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
.publish-card { margin-top: 16px; padding: 14px 16px; border: 1px solid var(--b-border, #d4e2f4); border-radius: 8px; background: #fff; }
.publish-card-head { display: flex; align-items: baseline; gap: 10px; margin-bottom: 10px; }
.section-title { margin: 0; font-size: 14px; font-weight: 600; }
.publish-count { font-size: 12px; color: var(--b-muted, #5c6370); }
.publish-list { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }
.publish-row { display: flex; align-items: center; gap: 12px; padding: 8px 10px; border-radius: 6px; background: var(--b-bg-subtle, #f5f9fe); }
.publish-row-meta { flex: 1 1 auto; min-width: 0; display: grid; gap: 2px; }
.publish-row-title { font-size: 13px; color: var(--b-neutral-text, #1a1d21); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.publish-row-code { font-size: 11px; color: var(--b-muted, #5c6370); font-family: ui-monospace, 'SF Mono', monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.publish-row-btn { flex-shrink: 0; }
.warn-panel { margin-top: 12px; padding: 10px 12px; border-radius: 6px; border: 1px solid #f0d080; background: #fff8e6; font-size: 13px; }
.warn-title { margin: 0 0 6px; font-size: 13px; font-weight: 600; color: #6b4e00; }
.warn-panel ul { margin: 0; padding-left: 18px; }
</style>
