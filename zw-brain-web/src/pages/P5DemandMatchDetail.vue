<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { authFetch } from '@/composables/useAuth';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailPanel from '@/components/DetailPanel.vue';
import DetailActions from '@/components/DetailActions.vue';
import { useProvider, useSnapshot } from '@/composables/useSnapshot';
import { demandRecordToProviderRow, deriveDemandMatches, type ProviderRow } from '@/lib/providerProjection';
import { invokeActionStub, pushToast } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';
import { canPerformAction } from '@/lib/pageAccess';
import { mapDetailRows } from '@/lib/detailDisplay';
import { formatTodoStatus } from '@/lib/statusLabels';
import { apiUrl } from '@/composables/useApiBase';

const route = useRoute();
const id = computed(() => String(route.params.id ?? ''));
const provider = useProvider();
const { source } = useSnapshot();
const currentRole = getProductRole();
const fetchedItem = ref<ProviderRow | null>(null);
const detailLoading = ref(false);
const detailLoaded = ref(false);

const inboxItem = computed(() =>
  deriveDemandMatches(provider.value as Record<string, unknown>).find((d) => d.id === id.value),
);
const item = computed(() => fetchedItem.value ?? inboxItem.value);
const isPendingResponse = computed(() => (item.value?.response_status ?? item.value?.status) === 'pending_response');
const canRespondDemand = computed(() => canPerformAction('demand.response.submit', currentRole.value) && isPendingResponse.value);

watch(
  [id, currentRole],
  async ([demandId, role]) => {
    fetchedItem.value = null;
    detailLoaded.value = false;
    if (!demandId) return;
    detailLoading.value = true;
    try {
      const resp = await authFetch(apiUrl('/api/skills/demand.list'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ role, confirmed: true }),
      });
      if (!resp.ok) return;
      const data = (await resp.json()) as { items?: unknown[]; result?: { items?: unknown[] } };
      const records = data.items ?? data.result?.items ?? [];
      const hit = records.find((row) => demandRecordToProviderRow(row).id === demandId);
      fetchedItem.value = hit ? demandRecordToProviderRow(hit) : null;
    } catch {
      // 收件箱投影仍可兜底；错误态不把页面打成“未找到”。
    } finally {
      detailLoaded.value = true;
      detailLoading.value = false;
    }
  },
  { immediate: true },
);

// 需求记录本身不携带「已匹配的本地资源」——先检索目录命中一条真实资源，
// 再把 catalog_code 写回供需响应。禁写死 resource_id（旧 bug：res-jbxx-ledger 全绑同一资源）。
const matchedResourceName = ref<string | null>(null);
const matching = ref(false);
const responseNote = ref('');
const resourceRef = ref('');

const rows = computed(() => {
  const it = item.value;
  if (!it) return [];
  const raw = [
    { label: '需求编号', value: it.id },
    { label: '需求标题', value: it.title },
    { label: '申请部门', value: it.applicant_dept || '—' },
    { label: '期望资源', value: it.target_resource_hint || '—' },
    { label: '响应状态', value: formatTodoStatus(it.response_status ?? it.status) },
    { label: '提供方结论', value: it.provider_decision ? formatTodoStatus(it.provider_decision) : '待响应' },
    { label: '处理意见', value: it.provider_response_note || '—' },
    { label: '关联资源', value: it.provider_resource_ref || '—' },
  ];
  if (matchedResourceName.value) {
    raw.push({ label: '已匹配本地目录', value: matchedResourceName.value });
  }
  return mapDetailRows(raw);
});

const MATCH_STOP_WORDS = new Set(['信息', '数据', '资源', '目录', '共享', '查询', '服务', '需求', '申请']);
const MATCH_DOMAIN_WORDS = ['不动产', '交易', '登记', '备案', '房屋', '房产', '医疗', '救助', '低保', '户籍', '法人', '企业'];

function addMatchTerm(out: string[], seen: Set<string>, raw: string) {
  const term = raw.trim();
  if (term.length < 2) return;
  if (MATCH_STOP_WORDS.has(term)) return;
  if (seen.has(term)) return;
  seen.add(term);
  out.push(term.slice(0, 24));
}

function matchQueries(): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  const hint = item.value?.target_resource_hint ?? '';
  const title = item.value?.title ?? '';
  addMatchTerm(out, seen, hint);
  addMatchTerm(out, seen, title);
  for (const word of MATCH_DOMAIN_WORDS) {
    if (`${hint} ${title}`.includes(word)) addMatchTerm(out, seen, word);
  }
  const compact = title.replace(/[^\u4e00-\u9fffA-Za-z0-9]/g, '');
  for (const size of [4, 3, 2]) {
    for (let i = 0; i <= compact.length - size; i += 1) {
      addMatchTerm(out, seen, compact.slice(i, i + size));
      if (out.length >= 8) return out;
    }
  }
  return out;
}

async function matchCatalog() {
  const queries = matchQueries();
  if (!queries.length) {
    pushToast({ kind: 'info', title: '无法检索', detail: '该需求缺少标题，无法检索匹配目录。' });
    return;
  }
  matching.value = true;
  try {
    for (const q of queries) {
      const resp = await authFetch(
        apiUrl('/api/skills/catalog.entry.query'),
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify({
            role: currentRole.value,
            confirmed: true,
            query: q,
            lifecycle_status: 'active',
            limit: 1,
          }),
        },
      );
      if (!resp.ok) {
        // R-005a：不漏原始 HTTP 码（R12）。
        pushToast({ kind: 'error', title: '检索失败', detail: '目录检索暂不可用，请稍后重试。' });
        return;
      }
      const data = (await resp.json()) as { items?: Array<Record<string, unknown>>; result?: { items?: Array<Record<string, unknown>> } };
      const first = (data.items ?? data.result?.items ?? [])[0];
      if (first && first.catalog_code) {
        const catalogCode = String(first.catalog_code);
        matchedResourceName.value = String(first.title ?? first.catalog_code);
        resourceRef.value = catalogCode;
        pushToast({ kind: 'ok', title: '已匹配目录', detail: `命中「${matchedResourceName.value}」，可作为关联资源。` });
        return;
      }
    }
    matchedResourceName.value = null;
    pushToast({ kind: 'info', title: '未命中', detail: '本地目录暂无可匹配资源；请登记需求或人工对接。' });
  } catch {
    pushToast({ kind: 'error', title: '检索失败', detail: '目录检索暂不可用，请稍后重试。' });
  } finally {
    matching.value = false;
  }
}

function requireResponseNote(action: string): boolean {
  if (responseNote.value.trim()) return true;
  pushToast({ kind: 'warn', title: '请填写处理意见', detail: `${action}前需要写明处理意见。` });
  return false;
}

async function respondDemand(decision: 'provide' | 'reject' | 'need_fix') {
  if (!requireResponseNote(decision === 'provide' ? '确认提供' : decision === 'reject' ? '拒绝提供' : '驳回补正')) return;
  if (decision === 'provide' && !resourceRef.value.trim()) {
    pushToast({ kind: 'warn', title: '请填写关联资源', detail: '确认提供前需要填写或检索出关联资源编号。' });
    return;
  }
  const result = await invokeActionStub({
    skillId: 'demand.response.submit',
    payload: {
      demand_id: id.value,
      decision,
      response_note: responseNote.value.trim(),
      resource_ref: decision === 'provide' ? resourceRef.value.trim() : undefined,
    },
    successTitle: decision === 'provide' ? '已确认提供' : decision === 'reject' ? '已拒绝提供' : '已退回补正',
    refreshSnapshotAfter: true,
  });
  if (result.ok && result.data) {
    const data = result.data as Record<string, unknown>;
    const record = (data.result ?? data) as Record<string, unknown>;
    fetchedItem.value = demandRecordToProviderRow(record);
    detailLoaded.value = true;
  }
}
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/provider/inbox/demand-match">← 供需对接</a></nav>
    <section class="panel">
      <PageFocusHeader :title="item?.title ?? `需求 ${id}`" meta="确认提供、拒绝提供或退回补正" />

      <template v-if="(source === 'live' || detailLoaded) && item">
        <DetailPanel title="需求详情" :rows="rows" />
        <div v-if="canRespondDemand" class="response-box">
          <label for="resource-ref">关联资源编号</label>
          <input id="resource-ref" v-model="resourceRef" placeholder="确认提供时填写目录或资源编号" />
          <label for="response-note">处理意见</label>
          <textarea id="response-note" v-model="responseNote" rows="4" placeholder="请写明确认提供、拒绝提供或补正原因" />
        </div>
        <DetailActions v-if="canRespondDemand">
          <button type="button" class="gov-btn gov-btn-secondary" :disabled="matching" @click="matchCatalog">
            {{ matching ? '检索中……' : '检索匹配目录' }}
          </button>
          <button
            v-if="canRespondDemand"
            type="button"
            class="gov-btn gov-btn-primary"
            @click="respondDemand('provide')"
          >
            确认提供
          </button>
          <button v-if="canRespondDemand" type="button" class="gov-btn" @click="respondDemand('need_fix')">驳回补正</button>
          <button v-if="canRespondDemand" type="button" class="gov-btn gov-btn-danger" @click="respondDemand('reject')">拒绝提供</button>
        </DetailActions>
        <p v-if="canRespondDemand && !resourceRef" class="hint">确认提供前可先检索匹配目录，命中后会自动填入关联资源编号。</p>
        <p v-else-if="item.response_status === 'responded'" class="hint">该需求已完成响应，可返回收件箱继续处理其他待办。</p>
      </template>
      <p v-else-if="source === 'live' && detailLoaded" class="focus-empty">未找到该需求编号。</p>
      <p v-else-if="detailLoading" class="focus-empty">正在加载需求详情……</p>
      <p v-else class="focus-empty">等待数据装载……</p>
    </section>
  </main>
</template>

<style scoped>
.gov-btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid transparent; margin-right: 8px; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-secondary { background: #fff; border-color: var(--b-border, #d4e2f4); }
.gov-btn-danger { background: #fff; color: #b42318; border-color: #f0b8b3; }
.gov-btn:disabled { opacity: 0.55; cursor: not-allowed; }
.hint { font-size: 12px; color: var(--b-muted, #5c6370); margin: 8px 0 0; }
.response-box { margin-top: 12px; display: grid; gap: 6px; max-width: 560px; }
label { font-size: 13px; color: var(--b-muted, #5c6370); }
input, textarea {
  padding: 8px 10px;
  border: 1px solid var(--b-border, #d4e2f4);
  border-radius: 6px;
  font-size: 14px;
}
</style>
