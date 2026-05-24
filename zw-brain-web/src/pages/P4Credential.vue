<script setup lang="ts">
import { computed, ref, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import { authFetch } from '@/composables/useAuth';
import { invokeActionStub } from '@/composables/useActionStub';
import DetailPanel from '@/components/DetailPanel.vue';

const route = useRoute();
const reqId = computed(() => String(route.params.id ?? ''));
const credential = ref<Record<string, unknown> | null>(null);
const error = ref<string | null>(null);

async function load() {
  error.value = null;
  try {
    const resp = await authFetch(`/api/skills/credential.query?role=ROLE_ORGAN_OPERATER&request_id=${encodeURIComponent(reqId.value)}`, {
      headers: { Accept: 'application/json' },
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    credential.value = (await resp.json()) as Record<string, unknown>;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

onMounted(() => { void load(); });

const rows = computed(() => {
  const c = credential.value;
  if (!c) return [];
  const out: { label: string; value: string }[] = [];
  if (c.api_endpoint) out.push({ label: 'API 端点', value: String(c.api_endpoint) });
  if (c.api_key) out.push({ label: 'API Key', value: String(c.api_key) });
  if (c.quota) out.push({ label: '配额', value: String(c.quota) });
  if (c.expires_at) out.push({ label: '有效期', value: String(c.expires_at) });
  if (c.monitor_url) out.push({ label: '监控入口', value: String(c.monitor_url) });
  return out;
});

const curlSample = computed(() => {
  const c = credential.value;
  const endpoint = String(c?.api_endpoint ?? 'https://brain.example/api/v1/...');
  const key = String(c?.api_key ?? '<API_KEY>');
  return `curl -H "Authorization: Bearer ${key}" ${endpoint}`;
});

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
  <main class="page-shell">
    <nav class="crumbs"><a href="#/delivery-exchange">← 回到交付任务</a></nav>
    <header class="page-hero">
      <div class="page-kicker">P4 · 凭据领取</div>
      <h1 class="page-hero-title">{{ reqId }} 凭据</h1>
      <p class="page-hero-subtitle">API Key + curl / Python / Java 调用样例 + 配额 + 监控入口。</p>
    </header>

    <DetailPanel v-if="rows.length" title="凭据要素" subtitle="来自 /api/skills/credential.query" :rows="rows" />

    <section class="panel">
      <header><h2 class="panel-title">curl 调用样例</h2></header>
      <pre class="code-block">{{ curlSample }}</pre>
    </section>

    <section v-if="error" class="panel">
      <header><h2 class="panel-title">数据回退</h2></header>
      <p class="text-body text-zw-mute">credential.query 调用失败：{{ error }}（E2 凭据 handler 落地前显示默认骨架）</p>
    </section>

    <section class="panel">
      <header><h2 class="panel-title">下一步</h2></header>
      <div class="actions">
        <button type="button" class="gov-btn gov-btn-primary" data-skill="credential.issue" @click="reissue">重新签发</button>
      </div>
    </section>
  </main>
</template>

<style scoped>
.page-shell { display: grid; gap: 16px; }
.crumbs a { font-size: 13px; color: var(--b-primary, #006be6); text-decoration: none; }
.code-block { background: #1a1d21; color: #d4e2f4; padding: 12px; border-radius: 6px; font-family: 'JetBrains Mono', Consolas, monospace; font-size: 12px; overflow-x: auto; margin: 12px 0 0; }
.actions { display: flex; gap: 8px; margin-top: 12px; }
.gov-btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid transparent; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
</style>
