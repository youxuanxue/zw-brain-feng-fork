<script setup lang="ts">
import { computed, ref, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import { authFetch } from '@/composables/useAuth';
import { invokeActionStub } from '@/composables/useActionStub';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailPanel from '@/components/DetailPanel.vue';
import DetailActions from '@/components/DetailActions.vue';
import { mapDetailRows } from '@/lib/detailDisplay';

interface CredentialQueryView {
  request_id: string;
  credential: Record<string, unknown> | null;
  status: string;
  hint?: string;
  issued_at?: string;
  issued_by?: string;
  resource_id?: string;
  resource_name?: string;
}

interface SampleRenderView {
  status: string;
  hint?: string;
  samples?: { curl?: string; python?: string; java?: string };
  monitoring_link?: string;
  monitoring_hint?: string;
  credential_excerpt?: Record<string, unknown>;
  invoke_url?: string;
}

const route = useRoute();
const reqId = computed(() => String(route.params.id ?? ''));
const credentialView = ref<CredentialQueryView | null>(null);
const sampleView = ref<SampleRenderView | null>(null);
const error = ref<string | null>(null);

async function load() {
  error.value = null;
  sampleView.value = null;
  try {
    const resp = await authFetch(
      `/api/skills/credential.query?role=ROLE_ORGAN_OPERATER&request_id=${encodeURIComponent(reqId.value)}`,
      { headers: { Accept: 'application/json' } },
    );
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    credentialView.value = (await resp.json()) as CredentialQueryView;

    if (credentialView.value.credential) {
      const sresp = await authFetch('/api/skills/credential.sample.render', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ request_id: reqId.value, role: 'ROLE_ORGAN_OPERATER', confirmed: true }),
      });
      if (sresp.ok) {
        sampleView.value = (await sresp.json()) as SampleRenderView;
      }
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

onMounted(() => { void load(); });

const cred = computed(() => credentialView.value?.credential ?? null);

const rows = computed(() => {
  const c = cred.value;
  const view = credentialView.value;
  if (!c && !view?.hint) return [];
  const out: { label: string; value: string }[] = [];
  if (view?.status) out.push({ label: '状态', value: view.status });
  if (view?.resource_name) out.push({ label: '资源', value: String(view.resource_name) });
  if (c?.app_key) out.push({ label: 'App Key', value: String(c.app_key) });
  if (c?.app_secret) out.push({ label: 'App Secret', value: String(c.app_secret) });
  if (c?.quota_per_day !== undefined) out.push({ label: '日配额', value: String(c.quota_per_day) });
  if (c?.valid_from) out.push({ label: '生效', value: String(c.valid_from) });
  if (c?.valid_to) out.push({ label: '失效', value: String(c.valid_to) });
  if (view?.issued_at) out.push({ label: '签发时间', value: String(view.issued_at) });
  if (sampleView.value?.monitoring_link) out.push({ label: '监控入口', value: String(sampleView.value.monitoring_link) });
  if (!c && view?.hint) out.push({ label: '提示', value: String(view.hint) });
  return mapDetailRows(out);
});

const curlSample = computed(() => sampleView.value?.samples?.curl ?? '');
const pythonSample = computed(() => sampleView.value?.samples?.python ?? '');
const javaSample = computed(() => sampleView.value?.samples?.java ?? '');

async function reissue() {
  await invokeActionStub({
    skillId: 'credential.issue',
    payload: { request_id: reqId.value },
    successTitle: '已重发凭据',
    pendingBackend: 'E2 凭据 (e2/plan.yaml F5)',
  });
  await load();
}
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/delivery-exchange">← 交付任务</a></nav>
    <section class="panel">
      <PageFocusHeader :title="`${reqId} 凭据`" meta="API Key · 调用样例 · 配额与监控" />
      <p v-if="error" class="focus-empty">{{ error }}</p>
      <DetailPanel v-if="rows.length" title="凭据要素" :rows="rows" />

      <section v-if="curlSample || pythonSample || javaSample" class="detail-block">
      <div v-if="curlSample" class="code-wrap">
        <h2 class="sub-title">curl</h2>
        <pre class="code-block">{{ curlSample }}</pre>
      </div>
      <div v-if="pythonSample" class="code-wrap">
        <h2 class="sub-title">Python</h2>
        <pre class="code-block">{{ pythonSample }}</pre>
      </div>
      <div v-if="javaSample" class="code-wrap">
        <h2 class="sub-title">Java</h2>
        <pre class="code-block">{{ javaSample }}</pre>
      </div>
      <p v-if="sampleView?.monitoring_hint" class="monitor-hint">{{ sampleView.monitoring_hint }}</p>
      <p v-if="sampleView?.monitoring_link">
        <a :href="sampleView.monitoring_link" target="_blank" rel="noopener noreferrer">打开运维监控</a>
      </p>
      </section>
      <DetailActions>
        <button type="button" class="gov-btn gov-btn-primary" @click="reissue">重新签发</button>
      </DetailActions>
    </section>
  </main>
</template>

<style scoped>
.sub-title { margin: 16px 0 6px; font-size: 14px; font-weight: 600; }
.code-wrap:first-of-type .sub-title { margin-top: 8px; }
.code-block { background: #1a1d21; color: #d4e2f4; padding: 12px; border-radius: 6px; font-family: 'JetBrains Mono', Consolas, monospace; font-size: 12px; overflow-x: auto; margin: 0; white-space: pre-wrap; }
.monitor-hint { font-size: 13px; color: var(--b-muted, #5c6370); margin: 12px 0 0; }
.gov-btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid transparent; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
</style>
