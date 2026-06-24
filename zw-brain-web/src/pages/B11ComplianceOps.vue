<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useAuditAccountability, useAuditAnomaly, useAuditReplay, useAuditStatistics } from '@/composables/useAuditPanels';
import { useInvestigationSummary } from '@/composables/useInvestigationSummary';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DataSourceBadge from '@/components/DataSourceBadge.vue';
import NLAcceleratorPanel from '@/components/NLAcceleratorPanel.vue';
import { consumeNLAction } from '@/lib/consumeNLAction';
import { pushToast } from '@/composables/useActionStub';
import { formatTime } from '@/lib/userLanguage';
import {
  formatActorLabel,
  formatAuditClass,
  formatCapabilityName,
  formatDeniedChainCount,
  formatDimension,
  formatPhase,
  formatRule,
  formatSeverity,
} from '@/lib/auditDisplay';

// 查审计拆分（P8·P9，Wave1-S3）：网关运行 / 服务调用监控面已拆出独立页 B13ServiceOps.vue
// （/service-ops，平台运维员 + 业务运营员 + 管理员/审计只读）。本页只保审计日志 / 证据回放 /
// 审计事件面，角色门收窄到业务运营员 + 安全审计员（productShellNav compliance-ops.roles）。
type PanelKind = 'replay' | 'statistics' | 'anomaly' | 'accountability';

const panelTabs: PanelKind[] = ['statistics', 'anomaly', 'accountability', 'replay'];

const activePanel = ref<PanelKind>('statistics');

const NL_PRESETS_B11 = ['看本周高风险异常', '近 24h 失败热点', '溯源 REQ-2026-04-25-0011'];

const replay = useAuditReplay();
const statistics = useAuditStatistics();
const anomaly = useAuditAnomaly();
const accountability = useAuditAccountability();
const summary = useInvestigationSummary();

const replayRequestId = ref('REQ-SD-GOV-001');
const statBucket = ref<'hour' | 'day' | 'week' | 'month'>('day');
const accountActor = ref('');

onMounted(() => {
  void statistics.load(statBucket.value);
  void anomaly.load();
  void replay.load(replayRequestId.value);
});

function switchPanel(p: PanelKind): void {
  activePanel.value = p;
  summary.reset();
}

async function refreshActive(): Promise<void> {
  if (activePanel.value === 'replay') await replay.load(replayRequestId.value);
  else if (activePanel.value === 'statistics') await statistics.load(statBucket.value);
  else if (activePanel.value === 'anomaly') await anomaly.load();
  else if (activePanel.value === 'accountability' && accountActor.value.trim()) {
    await accountability.load(accountActor.value.trim());
  }
}

async function traceActor(actor: string): Promise<void> {
  const normalized = String(actor ?? '').trim();
  if (!normalized) return;
  accountActor.value = normalized;
  activePanel.value = 'accountability';
  summary.reset();
  await accountability.load(normalized);
}

async function replayRequest(requestId: string): Promise<void> {
  const normalized = String(requestId ?? '').trim();
  if (!normalized) return;
  replayRequestId.value = normalized;
  activePanel.value = 'replay';
  summary.reset();
  await replay.load(normalized);
}

async function runSummary(): Promise<void> {
  if (activePanel.value === 'replay') {
    pushToast({ kind: 'info', title: '该视图不走 AI 摘要', detail: '请切到统计 / 异常 / 追责再触发摘要' });
    return;
  }
  const panelData =
    activePanel.value === 'statistics'
      ? statistics.data.value
      : activePanel.value === 'anomaly'
        ? anomaly.data.value
        : accountability.data.value;
  if (!panelData) {
    pushToast({ kind: 'warn', title: '当前视图尚无数据', detail: '请先点刷新装载面板数据' });
    return;
  }
  await summary.load(
    activePanel.value as 'statistics' | 'anomaly' | 'accountability',
    panelData as unknown as Record<string, unknown>
  );
}


const statisticsTotalRow = computed(() => {
  const t = statistics.data.value?.totals ?? {};
  return Object.entries(t).map(([k, v]) => ({ key: k, value: v }));
});

const severityRank: Record<string, number> = { high: 0, medium: 1, low: 2 };
const sortedAnomalies = computed(() => {
  const list = anomaly.data.value?.anomalies ?? [];
  return [...list].sort((a, b) => {
    const ra = severityRank[a.severity] ?? 9;
    const rb = severityRank[b.severity] ?? 9;
    if (ra !== rb) return ra - rb;
    return (b.occurrence_count ?? 0) - (a.occurrence_count ?? 0);
  });
});

const accountabilityEmptyText = computed(() => {
  // R-007：故障态不复用「无拒绝记录」这类正向空态文案（会误导成"查到了、没问题"）。
  if (accountability.source.value === 'error') return '数据暂不可用，请稍后重试。';
  const total = accountability.data.value?.total ?? 0;
  return formatDeniedChainCount(total);
});
</script>

<template>
  <main class="focus-page">
    <section class="panel panel-stack">
      <PageFocusHeader title="合规与运营" meta="统计 · 异常 · 追责 · 回放">
        <template #aside>
          <NLAcceleratorPanel page-anchor="B1.1" :presets="NL_PRESETS_B11" @action="consumeNLAction" />
        </template>
      </PageFocusHeader>

      <div class="focus-tab-row">
        <nav class="focus-tabs" role="tablist">
          <button
            v-for="p in panelTabs"
            :key="p"
            type="button"
            role="tab"
            class="focus-tab"
            :class="{ active: activePanel === p }"
            :aria-selected="activePanel === p"
            @click="switchPanel(p)"
          >
            {{ p === 'statistics' ? '统计' : p === 'anomaly' ? '异常' : p === 'accountability' ? '追责' : '回放' }}
          </button>
        </nav>
        <button type="button" class="focus-tab refresh-btn" @click="refreshActive">刷新</button>
      </div>

      <section v-show="activePanel === 'statistics'" class="focus-section">
        <header class="focus-section-head">
          <h2 class="focus-section-title">审计统计</h2>
          <div class="focus-section-controls">
            <label>时间粒度：
              <select v-model="statBucket" @change="statistics.load(statBucket)">
                <option value="hour">小时</option>
                <option value="day">日</option>
                <option value="week">周</option>
                <option value="month">月</option>
              </select>
            </label>
            <DataSourceBadge :source="statistics.source.value" />
          </div>
        </header>
        <div v-if="statistics.data.value" class="stat-block">
          <p class="focus-prose">
            扫描事件 <strong>{{ statistics.data.value.scanned }}</strong> 条；按
            <span class="tech-id">{{ formatDimension(statistics.data.value.dimension) }}</span> 维度聚合。
          </p>
          <table class="focus-ops-table">
            <thead><tr><th>时间桶</th><th>总数</th><th>分布</th></tr></thead>
            <tbody>
              <tr v-for="b in statistics.data.value.buckets" :key="b.bucket_key">
                <td><span class="tech-id">{{ b.bucket_key }}</span></td>
                <td>{{ b.total }}</td>
                <td>
                  <span v-for="(v, k) in b.by_dimension" :key="k" class="status-pill">{{ formatAuditClass(String(k)) }}: {{ v }}</span>
                </td>
              </tr>
            </tbody>
          </table>
          <div class="totals-row">
            <strong>累计：</strong>
            <span v-for="t in statisticsTotalRow" :key="t.key" class="status-pill">{{ formatAuditClass(t.key) }}: {{ t.value }}</span>
          </div>
        </div>
        <p v-else-if="statistics.source.value === 'error'" class="focus-prose focus-prose--muted">数据暂不可用，请稍后重试。</p>
        <p v-else class="focus-prose focus-prose--muted">等待装载……</p>
      </section>

      <section v-show="activePanel === 'anomaly'" class="focus-section">
        <header class="focus-section-head">
          <h2 class="focus-section-title">异常与督查</h2>
          <DataSourceBadge :source="anomaly.source.value" />
        </header>
        <div v-if="anomaly.data.value && anomaly.data.value.anomalies.length">
          <p class="focus-prose">
            扫描事件 <strong>{{ anomaly.data.value.scanned }}</strong> 条；命中
            <strong>{{ anomaly.data.value.anomalies.length }}</strong> 项异常。
          </p>
          <ul class="anom-list">
            <li v-for="(a, idx) in sortedAnomalies" :key="idx" :class="['anom-item', `severity-${a.severity}`]">
              <header>
                <span class="rule-tag">{{ formatRule(a.rule) }}</span>
                <span class="severity-tag">{{ formatSeverity(a.severity) }}</span>
                <span class="occ">{{ a.occurrence_count }} 次</span>
              </header>
              <p class="anom-summary">{{ a.summary }}</p>
              <p class="anom-meta">
                关注对象：<span class="tech-id">{{ formatActorLabel(a.actor) }}</span>
                <template v-if="a.skill_id"> · 能力 <span class="tech-id" :title="a.skill_id">{{ formatCapabilityName(a.skill_id) }}</span></template>
                <button type="button" class="inline-link" @click="traceActor(a.actor)">追责</button>
              </p>
              <p class="anom-meta">
                关联请求：
                <button
                  v-for="rid in a.evidence_request_ids"
                  :key="rid"
                  type="button"
                  class="tech-id evidence-rid request-chip"
                  @click="replayRequest(rid)"
                >{{ rid }}</button>
              </p>
            </li>
          </ul>
        </div>
        <p v-else-if="anomaly.source.value === 'error'" class="focus-prose focus-prose--muted">数据暂不可用，请稍后重试。</p>
        <p v-else class="focus-prose focus-prose--muted">当前窗口无异常。</p>
      </section>

      <section v-show="activePanel === 'accountability'" class="focus-section">
        <header class="focus-section-head">
          <h2 class="focus-section-title">追责链路</h2>
          <div class="focus-section-controls">
            <label>关注对象：
              <input
                v-model="accountActor"
                type="text"
                placeholder="从异常列表点「追责」带入"
                @change="accountActor.trim() && accountability.load(accountActor.trim())"
              />
            </label>
            <DataSourceBadge :source="accountability.source.value" />
          </div>
        </header>
        <p class="field-help">关注对象来自异常列表的“关注对象”或审计事件中的操作人；不用手工猜账号。</p>
        <div v-if="accountability.data.value && accountability.data.value.total > 0">
          <p class="focus-prose">
            关注对象 <span class="tech-id">{{ formatActorLabel(accountability.data.value.actor) }}</span>，
            {{ formatDeniedChainCount(accountability.data.value.total) }}
          </p>
          <ul class="chain-list">
            <li v-for="chain in accountability.data.value.denied_chains" :key="chain.request_id" class="chain-item">
              <header>
                <span class="tech-id chain-rid">{{ chain.request_id }}</span>
                <span class="status-pill" :title="chain.skill_id">{{ formatCapabilityName(chain.skill_id) }}</span>
                <time>{{ formatTime(chain.denied_at) }}</time>
                <button type="button" class="inline-link" @click="replayRequest(chain.request_id)">回放</button>
              </header>
              <ol class="chain-events">
                <li v-for="(ev, i) in chain.events" :key="i">
                  <span class="phase">{{ formatPhase(ev.phase) }}</span>
                  <time>{{ formatTime(ev.occurred_at) }}</time>
                  <pre class="sanitized">{{ JSON.stringify(ev.sanitized_payload, null, 2) }}</pre>
                </li>
              </ol>
            </li>
          </ul>
        </div>
        <p v-else class="focus-prose focus-prose--muted">{{ accountabilityEmptyText }}</p>
      </section>

      <section v-show="activePanel === 'replay'" class="focus-section">
        <header class="focus-section-head">
          <h2 class="focus-section-title">审计链回放</h2>
          <div class="focus-section-controls">
            <label>请求编号：
              <input v-model="replayRequestId" type="text" placeholder="从追责链点「回放」带入" @change="replay.load(replayRequestId)" />
            </label>
            <DataSourceBadge :source="replay.source.value" />
          </div>
        </header>
        <p class="field-help">请求编号来自异常列表的“关联请求”、追责链每条记录左侧编号，或业务操作失败时的请求编号。</p>
        <div v-if="replay.data.value">
          <p class="focus-prose">
            请求 <span class="tech-id">{{ replay.data.value.request_id }}</span> 共
            <strong>{{ replay.data.value.items.length }}</strong> 个阶段。
          </p>
          <ol class="replay-list">
            <li v-for="(ev, i) in replay.data.value.items" :key="i" class="replay-item">
              <header>
                <span class="phase">{{ formatPhase(ev.phase) }}</span>
                <time>{{ formatTime(ev.occurred_at) }}</time>
                <span class="status-pill">{{ formatAuditClass(ev.audit_class) }}</span>
              </header>
              <p class="replay-actor">
                <span class="tech-id">{{ formatActorLabel(ev.actor) }}</span>
                <template v-if="ev.skill_id"> · <span class="tech-id" :title="ev.skill_id">{{ formatCapabilityName(ev.skill_id) }}</span></template>
              </p>
              <pre class="replay-payload">{{ JSON.stringify(ev.payload, null, 2) }}</pre>
            </li>
          </ol>
        </div>
        <p v-else-if="replay.source.value === 'error'" class="focus-prose focus-prose--muted">数据暂不可用，请稍后重试。</p>
        <p v-else class="focus-prose focus-prose--muted">等待装载……</p>
      </section>

      <section class="focus-section focus-section--accent">
        <header class="focus-section-head">
          <h2 class="focus-section-title">调查摘要助手 <span class="assistant-tag">AI 辅助</span></h2>
          <div class="focus-section-controls">
            <button type="button" class="gov-btn gov-btn-primary" @click="runSummary">就当前视图生成摘要</button>
            <DataSourceBadge v-if="summary.source.value !== 'idle'" :source="summary.source.value" />
          </div>
        </header>
        <p class="focus-prose focus-prose--muted assistant-disclaimer">
          助手摘要不替代上方原始审计证据；文中的脱敏指纹字段为稳定哈希，按原文保留不还原。
        </p>
        <div v-if="summary.data.value" class="assistant-result">
          <p class="assistant-summary">{{ summary.data.value.summary }}</p>
          <p class="assistant-meta">
            模型 <span class="tech-id">{{ summary.data.value.model }}</span> · 输入指纹
            <span class="tech-id">{{ summary.data.value.sanitized_input_digest }}</span>
          </p>
        </div>
        <p v-else-if="summary.source.value === 'loading'" class="focus-prose focus-prose--muted">正在生成……</p>
        <p v-else class="focus-prose focus-prose--muted">点击上方按钮就当前视图生成摘要。</p>
      </section>
    </section>
  </main>
</template>

<style scoped>
.totals-row { margin-top: 12px; font-size: 13px; }
.anom-list { list-style: none; padding: 0; margin: 12px 0 0; display: grid; gap: 10px; }
.anom-item {
  padding: 14px;
  border-radius: 6px;
  background: #fff;
  border: 1px solid var(--b-border, #d4e2f4);
  border-left: 4px solid var(--b-border, #d4e2f4);
}
.anom-item.severity-high { border-left-color: #d9534f; }
.anom-item.severity-medium { border-left-color: #f0ad4e; }
.anom-item.severity-low { border-left-color: #5cb85c; }
.anom-item header { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.rule-tag { background: var(--b-primary, #006be6); color: #fff; font-size: 11px; padding: 2px 6px; border-radius: 4px; }
.severity-tag { font-size: 11px; padding: 2px 6px; border-radius: 4px; background: var(--b-bg-subtle, #e8f2fc); color: var(--b-muted, #5c6370); }
.occ { margin-left: auto; font-size: 12px; color: var(--b-muted, #5c6370); }
.anom-summary { margin: 8px 0 4px; font-size: 14px; line-height: 1.55; }
.anom-meta { margin: 4px 0; font-size: 13px; color: var(--b-muted, #5c6370); line-height: 1.5; }
.evidence-rid { margin-right: 6px; }
.field-help { margin: -2px 0 10px; font-size: 12px; color: var(--b-muted, #5c6370); }
.inline-link {
  border: 0;
  background: transparent;
  color: var(--b-primary, #006be6);
  font-size: 12px;
  cursor: pointer;
  padding: 0 0 0 8px;
  text-decoration: underline;
}
.request-chip {
  border: 0;
  background: transparent;
  color: var(--b-primary, #006be6);
  cursor: pointer;
  padding: 0;
  font-size: 12px;
}
.chain-list { list-style: none; padding: 0; margin: 12px 0 0; display: grid; gap: 12px; }
.chain-item { padding: 14px; background: #fff; border-radius: 6px; border: 1px solid var(--b-border, #d4e2f4); }
.chain-item header { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; font-size: 12px; flex-wrap: wrap; }
.chain-events { list-style: decimal; margin: 0; padding-left: 20px; font-size: 12px; }
.chain-events li { margin: 6px 0; }
.phase { display: inline-block; font-weight: 600; min-width: 60px; }
.sanitized, .replay-payload {
  background: #f7f8fb;
  padding: 8px;
  border-radius: 4px;
  font-family: ui-monospace, 'SF Mono', monospace;
  font-size: 11px;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 6px 0 0;
}
.replay-list { list-style: none; padding: 0; margin: 12px 0 0; display: grid; gap: 10px; }
.replay-item { padding: 14px; background: #fff; border-radius: 6px; border: 1px solid var(--b-border, #d4e2f4); border-left: 3px solid var(--b-primary, #006be6); }
.replay-item header { display: flex; gap: 8px; align-items: center; font-size: 12px; flex-wrap: wrap; }
.replay-actor { margin: 6px 0 0; font-size: 13px; color: var(--b-muted, #5c6370); }
.assistant-tag { font-size: 11px; padding: 2px 6px; background: #fff3cd; color: #856404; border-radius: 4px; margin-left: 8px; font-weight: 600; }
.assistant-disclaimer { margin: 0 0 12px; }
.assistant-result { padding: 14px; background: var(--b-bg-subtle, #e8f2fc); border-radius: 6px; }
.assistant-summary { font-size: 14px; line-height: 1.65; margin: 0; }
.assistant-meta { font-size: 12px; color: var(--b-muted, #5c6370); margin: 8px 0 0; line-height: 1.5; }
.gov-btn { padding: 6px 12px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid transparent; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
</style>
