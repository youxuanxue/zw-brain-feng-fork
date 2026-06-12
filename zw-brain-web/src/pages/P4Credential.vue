<script setup lang="ts">
import { computed, ref, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import { authFetch } from '@/composables/useAuth';
import { invokeActionStub } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';
import { canPerformAction } from '@/lib/pageAccess';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailPanel from '@/components/DetailPanel.vue';
import DetailActions from '@/components/DetailActions.vue';
import { mapDetailRows } from '@/lib/detailDisplay';
import { apiUrl } from '@/composables/useApiBase';

interface CredentialQueryView {
  request_id: string;
  credential: Record<string, unknown> | null;
  status: string;
  hint?: string;
  issued_at?: string;
  issued_by?: string;
  resource_id?: string;
  resource_name?: string;
  resource_kind?: string;
}

interface SampleRenderView {
  status: string;
  hint?: string;
  samples?: { curl?: string; python?: string; java?: string };
  monitoring_link?: string;
  monitoring_hint?: string;
  credential_excerpt?: Record<string, unknown>;
  invoke_url?: string;
  resource_kind?: string;
}

interface InvocationMetric {
  time_bucket?: string;
  resource_code?: string;
  invoke_count?: number;
  success_count?: number;
  failed_count?: number;
  error_count?: number;
  avg_latency_ms?: number;
}

interface InvocationQueryView {
  items?: InvocationMetric[];
  summary?: { invokeCount?: number; successCount?: number; failedCount?: number; errorCount?: number };
}

const route = useRoute();
const reqId = computed(() => String(route.params.id ?? ''));
const credentialView = ref<CredentialQueryView | null>(null);
const sampleView = ref<SampleRenderView | null>(null);
const error = ref<string | null>(null);

// 调用记录段（j1-api-call-monitoring）：诚实三态 loading / 数据 / 空，禁未到先显「暂无」。
const invocationView = ref<InvocationQueryView | null>(null);
const invocationLoading = ref(false);
const invocationError = ref<string | null>(null);
// 共性「无权 = 不可见」：credential.issue 仅 MANAGER+BUSIAUDIT，OPERATER 不应看到「重新签发」按钮
const canReissue = computed(() => canPerformAction('credential.issue', getProductRole().value));
// R-003「无权 = 不可见」：ops.service.invocation.query 仅 MANAGER+BUSIAUDIT+SECURITY_AUDIT；
// 申请人（OPERATER）无权，整段「调用记录」不渲染——不留一个查了恒返空/403 的死段。
const canViewInvocations = computed(() => canPerformAction('ops.service.invocation.query', getProductRole().value));

async function load() {
  error.value = null;
  sampleView.value = null;
  try {
    const resp = await authFetch(
      apiUrl(`/api/skills/credential.query?role=${encodeURIComponent(getProductRole().value)}&request_id=${encodeURIComponent(reqId.value)}`),
      { headers: { Accept: 'application/json' } },
    );
    if (!resp.ok) {
      // R-005a：禁把原始 `HTTP <code>` 漏进 UI（违 R12 工程术语）。按语义给诚实文案。
      // 422/404 = 该申请尚无交付任务/凭据（如历史导入或未到交付态）；403 = 无权。
      error.value =
        resp.status === 403
          ? '当前岗位无权查看该凭据。'
          : resp.status === 422 || resp.status === 404
            ? '该申请暂无可用凭据信息（尚未进入交付/签发环节）。'
            : '凭据信息暂不可用，请稍后重试。';
      return;
    }
    credentialView.value = (await resp.json()) as CredentialQueryView;

    if (credentialView.value.credential) {
      const sresp = await authFetch(apiUrl('/api/skills/credential.sample.render'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ request_id: reqId.value, role: getProductRole().value, confirmed: true }),
      });
      if (sresp.ok) {
        sampleView.value = (await sresp.json()) as SampleRenderView;
      }
      // 凭据已签发才有调用记录可看：用凭据绑定的资源 code 作过滤维度。
      // R-003：无权岗位不拉取（整段也不渲染）。
      if (canViewInvocations.value) void loadInvocations(credentialView.value.resource_id);
    }
  } catch {
    // R-005a：网络/解析异常也不漏原始信息，给诚实兜底文案。
    error.value = '凭据信息暂不可用，请稍后重试。';
  }
}

async function loadInvocations(resourceCode?: string): Promise<void> {
  invocationLoading.value = true;
  invocationError.value = null;
  invocationView.value = null;
  try {
    const params = new URLSearchParams({ role: getProductRole().value });
    if (resourceCode) params.set('resource_code', resourceCode);
    const resp = await authFetch(`/api/skills/ops.service.invocation.query?${params.toString()}`, {
      headers: { Accept: 'application/json' },
    });
    if (resp.status === 403) {
      invocationError.value = '当前岗位无权查看调用记录。';
      return;
    }
    if (resp.status === 404 || resp.status === 405 || resp.status === 501) {
      invocationError.value = '调用记录暂未在本环境开通。';
      return;
    }
    if (!resp.ok) {
      invocationError.value = '调用记录暂不可用，请稍后重试。';
      return;
    }
    invocationView.value = (await resp.json()) as InvocationQueryView;
  } catch {
    // R-005a：不漏原始 HTTP/异常信息。
    invocationError.value = '调用记录暂不可用，请稍后重试。';
  } finally {
    invocationLoading.value = false;
  }
}

onMounted(() => { void load(); });

const cred = computed(() => credentialView.value?.credential ?? null);

// F5（0605#9）：API 资源把凭据按「查看授权/授权码」呈现——网关 App Key/Secret
// 即调用授权要素，curl/Python/Java 样例就是授权后的调用方式。非 API（库表/文件）或未知
// 形态保持「凭据」通用词（诚实不臆断）。
const isApiResource = computed(() => String(credentialView.value?.resource_kind ?? '').toLowerCase() === 'api');
const authNoun = computed(() => (isApiResource.value ? '授权' : '凭据'));
const authPanelTitle = computed(() => (isApiResource.value ? '授权要素（网关授权码）' : '凭据要素'));
const headerNoun = computed(() => (isApiResource.value ? '授权' : '凭据'));
const headerSubMeta = computed(() =>
  isApiResource.value ? '网关授权码（App Key / Secret）· 调用样例 · 配额与监控' : 'App Key · 调用样例 · 配额与监控',
);

const rows = computed(() => {
  const c = cred.value;
  const view = credentialView.value;
  if (!c && !view?.hint) return [];
  const out: { label: string; value: string }[] = [];
  if (view?.status) out.push({ label: '状态', value: view.status });
  if (view?.resource_name) out.push({ label: '资源', value: String(view.resource_name) });
  if (c?.app_key) out.push({ label: isApiResource.value ? '网关 App Key' : 'App Key', value: String(c.app_key) });
  if (c?.app_secret) out.push({ label: isApiResource.value ? '网关 App Secret' : 'App Secret', value: String(c.app_secret) });
  if (c?.quota_per_day !== undefined) out.push({ label: '日配额', value: String(c.quota_per_day) });
  if (c?.valid_from) out.push({ label: '生效', value: String(c.valid_from) });
  if (c?.valid_to) out.push({ label: '失效', value: String(c.valid_to) });
  if (view?.issued_at) out.push({ label: '签发时间', value: String(view.issued_at) });
  if (sampleView.value?.monitoring_link) out.push({ label: '监控入口', value: String(sampleView.value.monitoring_link) });
  if (!c && view?.hint) out.push({ label: '提示', value: String(view.hint) });
  return mapDetailRows(out);
});

const invocationRows = computed(() => invocationView.value?.items ?? []);
const invocationSummary = computed(() => invocationView.value?.summary ?? null);
const hasCredential = computed(() => Boolean(credentialView.value?.credential));

function fmtLatency(ms?: number): string {
  if (ms === undefined || ms === null) return '—';
  return `${Math.round(Number(ms))} 毫秒`;
}

const curlSample = computed(() => sampleView.value?.samples?.curl ?? '');
const pythonSample = computed(() => sampleView.value?.samples?.python ?? '');
const javaSample = computed(() => sampleView.value?.samples?.java ?? '');

// 「提异议」入口拆两路：资源维度（带 resource_id）+ 交付维度（带 request_id）。
// resource_id 在 view 装载后才有，未到位时只给交付维度入口。
const objectionLinks = computed(() => {
  const links: { label: string; href: string }[] = [];
  const req = encodeURIComponent(reqId.value);
  if (req) {
    links.push({ label: '提交付异议', href: `#/request-flow/objection/new?type=delivery&id=${req}` });
  }
  const resId = credentialView.value?.resource_id;
  if (resId) {
    const r = encodeURIComponent(String(resId));
    links.push({ label: '提资源异议', href: `#/request-flow/objection/new?type=resource&id=${r}` });
  }
  return links;
});

async function reissue() {
  await invokeActionStub({
    skillId: 'credential.issue',
    payload: { request_id: reqId.value },
    successTitle: `已重发${authNoun.value}`,
  });
  await load();
}
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/delivery-exchange">← 交付任务</a></nav>
    <section class="panel">
      <PageFocusHeader
        :title="`${reqId} ${headerNoun}`"
        :meta="headerSubMeta"
        :links="objectionLinks"
      />
      <p v-if="error" class="focus-empty">{{ error }}</p>
      <DetailPanel v-if="rows.length" :title="authPanelTitle" :rows="rows" />

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

      <section v-if="hasCredential && canViewInvocations" class="detail-block invoke-records">
        <h2 class="sub-title">调用记录</h2>
        <p v-if="invocationLoading" class="focus-empty">加载中……</p>
        <p v-else-if="invocationError" class="focus-empty">{{ invocationError }}</p>
        <template v-else-if="invocationRows.length">
          <p v-if="invocationSummary" class="invoke-quota">
            累计调用 {{ invocationSummary.invokeCount ?? 0 }} 次 · 成功
            {{ invocationSummary.successCount ?? 0 }} · 失败 {{ invocationSummary.failedCount ?? 0 }}
          </p>
          <table class="invoke-table">
            <thead>
              <tr>
                <th>时段</th>
                <th>调用次数</th>
                <th>成功</th>
                <th>失败</th>
                <th>平均时延</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(m, i) in invocationRows" :key="i">
                <td>{{ m.time_bucket ?? '—' }}</td>
                <td>{{ m.invoke_count ?? 0 }}</td>
                <td>{{ m.success_count ?? 0 }}</td>
                <td :class="{ 'cell-danger': (m.failed_count ?? 0) > 0 }">{{ m.failed_count ?? 0 }}</td>
                <td>{{ fmtLatency(m.avg_latency_ms) }}</td>
              </tr>
            </tbody>
          </table>
        </template>
        <!-- R-002 诚实空态：当前专题包/资源凭据与网关 api_id 调用指标尚无映射，
             返回 0 行不等于「真的零调用」。如实说明「未接入」而非显示误导性的零，
             避免让人误读为该资源没人调用。映射打通（res→api_id）后才显真实统计。 -->
        <p v-else class="focus-empty">该资源暂未接入网关调用统计，调用记录将在映射开通后展示。</p>
      </section>

      <DetailActions v-if="canReissue">
        <button type="button" class="gov-btn gov-btn-primary" @click="reissue">重新签发{{ headerNoun }}</button>
      </DetailActions>
    </section>
  </main>
</template>

<style scoped>
.sub-title { margin: 16px 0 6px; font-size: 14px; font-weight: 600; }
.code-wrap:first-of-type .sub-title { margin-top: 8px; }
.code-block { background: #1a1d21; color: #d4e2f4; padding: 12px; border-radius: 6px; font-family: 'JetBrains Mono', Consolas, monospace; font-size: 12px; overflow-x: auto; margin: 0; white-space: pre-wrap; }
.monitor-hint { font-size: 13px; color: var(--b-muted, #5c6370); margin: 12px 0 0; }
.invoke-records { margin-top: 16px; }
.invoke-quota { font-size: 13px; color: var(--b-muted, #5c6370); margin: 0 0 10px; }
.invoke-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.invoke-table th, .invoke-table td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--b-border, #eef2f8); }
.invoke-table th { color: var(--b-muted, #5c6370); font-weight: 600; }
.cell-danger { color: var(--b-danger, #d4380d); font-weight: 600; }
.gov-btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid transparent; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
</style>
