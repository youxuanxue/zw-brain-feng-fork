<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRoute } from 'vue-router';
import { authFetch } from '@/composables/useAuth';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailPanel from '@/components/DetailPanel.vue';
import DetailActions from '@/components/DetailActions.vue';
import { useProvider, useSnapshot } from '@/composables/useSnapshot';
import { deriveDemandMatches } from '@/lib/providerProjection';
import { invokeActionStub, pushToast } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';
import { canPerformAction } from '@/lib/pageAccess';
import { mapDetailRows } from '@/lib/detailDisplay';

const route = useRoute();
const id = computed(() => String(route.params.id ?? ''));
const provider = useProvider();
const { source } = useSnapshot();

const item = computed(() =>
  deriveDemandMatches(provider.value as Record<string, unknown>).find((d) => d.id === id.value),
);
// request.create 仅 OPERATER；MANAGER/BUSIAUDIT 见不到「受理并起草申请」
const canAcceptDemand = computed(() => canPerformAction('request.create', getProductRole().value));

// 需求记录本身不携带「已匹配的本地资源」——必须先检索目录命中一条真实资源，
// 再用它的 catalog_code 起草申请。禁写死 resource_id（旧 bug：res-jbxx-ledger 全绑同一资源）。
const matchedResourceId = ref<string | null>(null);
const matchedResourceName = ref<string | null>(null);
const matching = ref(false);

const rows = computed(() => {
  const it = item.value;
  if (!it) return [];
  const raw = [
    { label: '需求编号', value: it.id },
    { label: '需求标题', value: it.title },
    { label: '来源平台', value: it.catalog },
    { label: '当前状态', value: it.status },
  ];
  if (matchedResourceName.value) {
    raw.push({ label: '已匹配本地目录', value: matchedResourceName.value });
  }
  return mapDetailRows(raw);
});

async function matchCatalog() {
  const q = item.value?.title?.slice(0, 24) ?? '';
  if (!q) {
    pushToast({ kind: 'info', title: '无法检索', detail: '该需求缺少标题，无法检索匹配目录。' });
    return;
  }
  matching.value = true;
  try {
    const resp = await authFetch(
      `/api/skills/catalog.entry.query?role=${encodeURIComponent(getProductRole().value)}&query=${encodeURIComponent(q)}&limit=1`,
      { headers: { Accept: 'application/json' } },
    );
    if (!resp.ok) {
      // R-005a：不漏原始 HTTP 码（R12）。
      pushToast({ kind: 'error', title: '检索失败', detail: '目录检索暂不可用，请稍后重试。' });
      return;
    }
    const data = (await resp.json()) as { items?: Array<Record<string, unknown>> };
    const first = data.items?.[0];
    if (first && first.catalog_code) {
      matchedResourceId.value = String(first.catalog_code);
      matchedResourceName.value = String(first.title ?? first.catalog_code);
      pushToast({ kind: 'ok', title: '已匹配目录', detail: `命中「${matchedResourceName.value}」，可起草申请。` });
    } else {
      matchedResourceId.value = null;
      matchedResourceName.value = null;
      pushToast({ kind: 'info', title: '未命中', detail: '本地目录暂无可匹配资源；请登记需求或人工对接。' });
    }
  } catch {
    pushToast({ kind: 'error', title: '检索失败', detail: '目录检索暂不可用，请稍后重试。' });
  } finally {
    matching.value = false;
  }
}

async function acceptDemand() {
  // 诚实门控：未先匹配到真实本地目录则不起草，避免错绑固定资源。
  if (!matchedResourceId.value) {
    pushToast({
      kind: 'info',
      title: '请先匹配目录',
      detail: '需先点「检索匹配目录」命中一条本地资源，再起草复用申请。',
    });
    return;
  }
  await invokeActionStub({
    skillId: 'request.create',
    payload: {
      resource_id: matchedResourceId.value,
      purpose: `对接国家需求 ${id.value}：${item.value?.title ?? ''}`.trim(),
    },
    successTitle: '已起草对接申请',
  });
}
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/provider/inbox/demand-match">← 供需对接</a></nav>
    <section class="panel">
      <PageFocusHeader :title="item?.title ?? `需求 ${id}`" meta="匹配本地目录后起草复用申请" />

      <template v-if="source === 'live' && item">
        <DetailPanel title="需求详情" :rows="rows" />
        <DetailActions>
          <button type="button" class="gov-btn gov-btn-secondary" :disabled="matching" @click="matchCatalog">
            {{ matching ? '检索中……' : '检索匹配目录' }}
          </button>
          <button
            v-if="canAcceptDemand"
            type="button"
            class="gov-btn gov-btn-primary"
            :disabled="!matchedResourceId"
            @click="acceptDemand"
          >
            受理并起草申请
          </button>
        </DetailActions>
        <p v-if="canAcceptDemand && !matchedResourceId" class="hint">先检索匹配本地目录，命中后方可起草复用申请。</p>
      </template>
      <p v-else-if="source === 'live'" class="focus-empty">未找到该需求编号。</p>
      <p v-else class="focus-empty">等待数据装载……</p>
    </section>
  </main>
</template>

<style scoped>
.gov-btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid transparent; margin-right: 8px; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-secondary { background: #fff; border-color: var(--b-border, #d4e2f4); }
.gov-btn:disabled { opacity: 0.55; cursor: not-allowed; }
.hint { font-size: 12px; color: var(--b-muted, #5c6370); margin: 8px 0 0; }
</style>
