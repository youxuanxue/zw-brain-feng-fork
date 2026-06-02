<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import { useSnapshot } from '@/composables/useSnapshot';
import { authFetch } from '@/composables/useAuth';
import { pushToast } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';
import { formatTodoStatus } from '@/lib/statusLabels';
import { apiUrl } from '@/composables/useApiBase';

// F9 真端到端：P7 直读 topic.package 后端（topic.package.query / subscribe），
// 不再读 snapshot.zones 静态字段（参照 P5CatalogReviewInbox 真 API 范式）。
const { source } = useSnapshot();
const role = getProductRole();

interface TopicPackageRow {
  packageCode: string;
  name: string;
  desc: string;
  status: string;
  catalogCount: number;
  isSubscribed: boolean;
}

const items = ref<TopicPackageRow[]>([]);
const loading = ref(false);
const errorMsg = ref('');
const subscribing = ref<Set<string>>(new Set());

async function loadPackages(): Promise<void> {
  loading.value = true;
  errorMsg.value = '';
  try {
    const resp = await authFetch(apiUrl('/api/skills/topic.package.query'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ role: role.value, status: 'published' }),
    });
    if (!resp.ok) {
      items.value = [];
      errorMsg.value = `加载失败：HTTP ${resp.status}`;
      return;
    }
    const body = (await resp.json()) as { items?: Array<Record<string, unknown>> };
    items.value = (body.items ?? [])
      .map((it) => ({
        packageCode: String(it.package_code ?? ''),
        name: String(it.title ?? it.package_code ?? ''),
        desc: String(it.scenario ?? ''),
        status: String(it.status ?? ''),
        catalogCount: Number(it.activeCatalogCount ?? 0),
        isSubscribed: Boolean(it.isSubscribed),
      }))
      .filter((it) => it.packageCode);
  } finally {
    loading.value = false;
  }
}

const headerMeta = computed(() => {
  if (source.value !== 'live') return '正在加载……';
  if (errorMsg.value) return errorMsg.value;
  if (loading.value) return '加载中……';
  return items.value.length ? `${items.value.length} 个专题可订阅` : '暂无专题包';
});

async function subscribe(packageCode: string): Promise<void> {
  if (subscribing.value.has(packageCode)) return;
  subscribing.value.add(packageCode);
  try {
    const resp = await authFetch(apiUrl('/api/skills/topic.package.subscribe'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ role: role.value, confirmed: true, package_code: packageCode }),
    });
    if (resp.ok) {
      pushToast({ kind: 'ok', title: '已订阅专题' });
      void loadPackages();
    } else if (resp.status === 404 || resp.status === 405 || resp.status === 501) {
      pushToast({ kind: 'warn', title: '暂不可用', detail: '该操作尚未在本环境开通，请稍后再试。' });
    } else {
      const data = (await resp.json().catch(() => ({}))) as Record<string, unknown>;
      pushToast({ kind: 'info', title: '操作未完成', detail: String(data.detail ?? '请检查当前岗位权限或稍后重试。') });
    }
  } catch (e) {
    pushToast({ kind: 'error', title: '调用失败', detail: e instanceof Error ? e.message : String(e) });
  } finally {
    subscribing.value.delete(packageCode);
  }
}

watch(source, (live) => {
  if (live === 'live') void loadPackages();
}, { immediate: true });

watch(role, () => {
  void loadPackages();
});
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
        <article v-for="z in items" :key="z.packageCode" class="zone-card">
          <header>
            <a :href="`#/zones-pack/zone/${encodeURIComponent(z.packageCode)}`" class="zone-title"><strong>{{ z.name || z.packageCode }}</strong></a>
            <span v-if="z.status" class="zone-status">{{ formatTodoStatus(z.status) }}</span>
          </header>
          <p v-if="z.desc" class="zone-desc">{{ z.desc }}</p>
          <p v-if="z.catalogCount" class="zone-meta">关联目录 {{ z.catalogCount }} 个</p>
          <footer class="row-actions">
            <button
              type="button"
              class="gov-btn gov-btn-primary"
              :disabled="subscribing.has(z.packageCode) || z.isSubscribed"
              @click="subscribe(z.packageCode)"
            >{{ subscribing.has(z.packageCode) ? '订阅中……' : z.isSubscribed ? '已订阅' : '订阅专题' }}</button>
            <a :href="`#/zones-pack/zone/${encodeURIComponent(z.packageCode)}`" class="gov-btn gov-btn-secondary">详情</a>
          </footer>
        </article>
      </div>
      <p v-else-if="source === 'live' && loading" class="focus-empty">加载中……</p>
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
.zone-meta { font-size: 12px; color: var(--b-muted, #5c6370); margin: 0; }
.gov-btn { padding: 4px 12px; border-radius: 6px; font-size: 12px; cursor: pointer; border: 1px solid transparent; text-decoration: none; display: inline-flex; align-items: center; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-primary:disabled { opacity: 0.6; cursor: default; }
.gov-btn-secondary { background: #fff; border-color: var(--b-border, #d4e2f4); }
</style>
