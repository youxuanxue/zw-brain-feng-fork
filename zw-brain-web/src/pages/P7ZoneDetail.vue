<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailPanel from '@/components/DetailPanel.vue';
import DetailActions from '@/components/DetailActions.vue';
import { useSnapshot } from '@/composables/useSnapshot';
import { authFetch } from '@/composables/useAuth';
import { pushToast } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';
import { mapDetailRows } from '@/lib/detailDisplay';
import { formatTodoStatus, todoStatusTone } from '@/lib/statusLabels';

// F9 真端到端：详情直读 topic.package.query（带 package_code），渲染真 items / visibility / metrics。
const route = useRoute();
const id = computed(() => String(route.params.id ?? ''));
const role = getProductRole();
const { source } = useSnapshot();

const detail = ref<Record<string, unknown> | null>(null);
const loading = ref(false);
const subscribing = ref(false);

async function loadDetail(): Promise<void> {
  if (!id.value) return;
  loading.value = true;
  try {
    const resp = await authFetch('/api/skills/topic.package.query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ role: role.value, package_code: id.value }),
    });
    if (!resp.ok) {
      detail.value = null;
      return;
    }
    const body = (await resp.json()) as { items?: Array<Record<string, unknown>> };
    detail.value = body.items?.[0] ?? null;
  } finally {
    loading.value = false;
  }
}

const statusText = computed(() => String(detail.value?.status ?? ''));
const isSubscribed = computed(() => Boolean(detail.value?.isSubscribed));

const rows = computed(() => {
  const d = detail.value;
  if (!d) return mapDetailRows([{ label: '专题编号', value: id.value }]);
  const visibleOrgCount = Number(d.visibleOrgCount ?? 0);
  return mapDetailRows([
    { label: '专题编号', value: String(d.package_code ?? id.value) },
    { label: '专题名称', value: String(d.title ?? '—') },
    { label: '应用场景', value: String(d.scenario ?? '—') },
    { label: '发布状态', value: formatTodoStatus(statusText.value) },
    { label: '可见组织数', value: visibleOrgCount ? String(visibleOrgCount) : '—' },
  ]);
});

const assets = computed(() => {
  const its = Array.isArray(detail.value?.items) ? (detail.value!.items as Array<Record<string, unknown>>) : [];
  // 只列目录名，不加链接：F9 专题包引用的目录尚未录入 catalog_entry 主表（不可检索、无
  // 详情页），任何"跳转查看"都无处可达。诚实展示，待 J1 目录主表录入后再补可达链接（下个 PR）。
  return its
    .map((it) => String(it.title ?? it.ref_id ?? ''))
    .filter(Boolean);
});

const trust = computed(() => {
  const vis = Array.isArray(detail.value?.visibility) ? (detail.value!.visibility as Array<Record<string, unknown>>) : [];
  return vis
    .filter((v) => v.policy_status === 'approved')
    .map((v) => {
      const org = String(v.org_code ?? '全部组织');
      const r = String(v.role_code ?? '全部角色');
      return `可见组织 ${org} · 角色 ${r}`;
    });
});

const headerTitle = computed(() => {
  if (detail.value?.title) return String(detail.value.title);
  if (source.value === 'live') return id.value;
  return '正在加载……';
});

const headerMeta = computed(() => {
  if (detail.value?.scenario) return String(detail.value.scenario);
  if (source.value === 'live' && !detail.value) return '未找到该专题';
  if (source.value !== 'live') return '正在加载专题详情……';
  return '';
});

const statusTone = computed(() => todoStatusTone(statusText.value));

async function subscribe(): Promise<void> {
  if (subscribing.value) return;
  subscribing.value = true;
  try {
    const resp = await authFetch('/api/skills/topic.package.subscribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ role: role.value, confirmed: true, package_code: id.value }),
    });
    if (resp.ok) {
      pushToast({ kind: 'ok', title: '已订阅专题' });
      void loadDetail();
    } else if (resp.status === 404 || resp.status === 405 || resp.status === 501) {
      pushToast({ kind: 'warn', title: '暂不可用', detail: '该操作尚未在本环境开通，请稍后再试。' });
    } else {
      const data = (await resp.json().catch(() => ({}))) as Record<string, unknown>;
      pushToast({ kind: 'info', title: '操作未完成', detail: String(data.detail ?? '请检查当前岗位权限或稍后重试。') });
    }
  } catch (e) {
    pushToast({ kind: 'error', title: '调用失败', detail: e instanceof Error ? e.message : String(e) });
  } finally {
    subscribing.value = false;
  }
}

watch([source, id], ([live]) => {
  if (live === 'live') void loadDetail();
}, { immediate: true });

watch(role, () => {
  void loadDetail();
});
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/zones-pack">← 共享专题包</a></nav>
    <section class="panel">
      <PageFocusHeader :title="headerTitle" :meta="headerMeta">
        <template v-if="statusText" #aside>
          <span class="zone-badge" :class="statusTone">{{ formatTodoStatus(statusText) }}</span>
        </template>
      </PageFocusHeader>

      <DetailPanel v-if="rows.length" title="基本信息" :rows="rows" />

      <section v-if="assets.length" class="detail-block">
        <h2 class="detail-block-title">包含目录</h2>
        <ul class="asset-list">
          <li v-for="a in assets" :key="a">{{ a }}</li>
        </ul>
        <p class="catalog-note">目录详情与检索入口待 J1 目录主表录入后开放。</p>
      </section>

      <section v-if="trust.length" class="detail-block">
        <h2 class="detail-block-title">可见性策略</h2>
        <ul class="hint-list">
          <li v-for="t in trust" :key="t">{{ t }}</li>
        </ul>
      </section>

      <DetailActions v-if="detail">
        <button type="button" class="gov-btn gov-btn-primary" :disabled="subscribing || isSubscribed" @click="subscribe">{{ subscribing ? '订阅中……' : isSubscribed ? '已订阅' : '订阅专题' }}</button>
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
.asset-list { list-style: disc; padding-left: 20px; margin: 8px 0 0; font-size: 14px; line-height: 1.6; }
.catalog-note { font-size: 12px; color: var(--b-muted, #5c6370); margin: 6px 0 0; font-style: italic; }
.hint-list { padding-left: 20px; margin: 8px 0 0; font-size: 14px; line-height: 1.6; }
.gov-btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid transparent; text-decoration: none; display: inline-flex; align-items: center; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-primary:disabled { opacity: 0.6; cursor: default; }
.gov-btn-secondary { background: #fff; border-color: var(--b-border, #d4e2f4); }
</style>
