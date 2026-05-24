<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useAuditAccountability, useAuditAnomaly, useAuditReplay, useAuditStatistics } from '@/composables/useAuditPanels';
import { useInvestigationSummary } from '@/composables/useInvestigationSummary';
import NLAcceleratorPanel from '@/components/NLAcceleratorPanel.vue';
import type { StructuredAction } from '@/composables/useNLAccelerator';
import { invokeActionStub, pushToast } from '@/composables/useActionStub';

// B1.1 合规与运营：4 面板 + 调查摘要助手；仅 ROLE_SECURITY_AUDIT / ROLE_BUSIAUDIT
// 可见（路由层 + BFF 兜底；F3-UI 本页直接调用后端 audit.event.* 5 capability +
// assistant.investigation_summary，6 个调用均 PR #91 ef9b706/58d5587 已 land main）。
//
// 设计意图（不覆盖原始审计证据）：调查摘要助手区与 4 面板原始数据**并列**
// 展示，永不替换原始证据；助手摘要 sha1: 字段按原文保留不还原。

type PanelKind = 'replay' | 'statistics' | 'anomaly' | 'accountability';

const activePanel = ref<PanelKind>('statistics');

const NL_PRESETS_B11 = ['看本周高风险异常', '近 24h 失败热点', '溯源 REQ-2026-04-25-0011'];

const replay = useAuditReplay();
const statistics = useAuditStatistics();
const anomaly = useAuditAnomaly();
const accountability = useAuditAccountability();
const summary = useInvestigationSummary();

const replayRequestId = ref('REQ-SD-GOV-001');
const statBucket = ref<'hour' | 'day' | 'week' | 'month'>('day');
const accountActor = ref('user:gov:ROLE_ORGAN_OPERATER:王凯');

onMounted(() => {
  void statistics.load(statBucket.value);
  void anomaly.load();
  void accountability.load(accountActor.value);
  void replay.load(replayRequestId.value);
});

function switchPanel(p: PanelKind): void {
  activePanel.value = p;
  summary.reset(); // 切面板时清空助手摘要，强制重新触发
}

async function refreshActive(): Promise<void> {
  if (activePanel.value === 'replay') await replay.load(replayRequestId.value);
  else if (activePanel.value === 'statistics') await statistics.load(statBucket.value);
  else if (activePanel.value === 'anomaly') await anomaly.load();
  else if (activePanel.value === 'accountability') await accountability.load(accountActor.value);
}

async function runSummary(): Promise<void> {
  if (activePanel.value === 'replay') {
    pushToast({ kind: 'info', title: '回放视图不走 AI 摘要', detail: '请切到统计 / 异常 / 追责再触发摘要' });
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

function consumeNLAction(action: StructuredAction): void {
  if (action.kind === 'invoke' && action.target) {
    void invokeActionStub({
      skillId: action.target,
      payload: action.payload,
      role: 'ROLE_SECURITY_AUDIT',
      successTitle: action.label,
    });
  } else if (action.kind === 'filter' || action.kind === 'draft') {
    pushToast({ kind: 'info', title: '已应用', detail: action.label });
  }
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
</script>

<template>
  <main class="page-shell">
    <header class="page-hero">
      <div class="hero-row">
        <div>
          <div class="page-kicker">B1.1 · 后台支撑面</div>
          <h1 class="page-hero-title">合规与运营</h1>
          <p class="page-hero-subtitle">审计回放 / 统计 / 异常 / 追责；仅安全审计员、平台运营员可见。</p>
        </div>
        <NLAcceleratorPanel page-anchor="B1.1" :presets="NL_PRESETS_B11" @action="consumeNLAction" />
      </div>
    </header>

    <div class="panel-tab-row">
      <nav class="panel-tabs" role="tablist">
        <button
          v-for="p in (['statistics', 'anomaly', 'accountability', 'replay'] as PanelKind[])"
          :key="p"
          type="button"
          role="tab"
          :class="['panel-tab', { active: activePanel === p }]"
          :aria-selected="activePanel === p"
          @click="switchPanel(p)"
        >
          {{ p === 'statistics' ? '统计' : p === 'anomaly' ? '异常' : p === 'accountability' ? '追责' : '回放' }}
        </button>
      </nav>
      <button type="button" class="panel-tab refresh-btn" @click="refreshActive">刷新</button>
    </div>

    <!-- 统计 -->
    <section v-show="activePanel === 'statistics'" class="panel">
      <header class="panel-head">
        <h2 class="panel-title">审计统计</h2>
        <div class="panel-controls">
          <label>时间桶：
            <select v-model="statBucket" @change="statistics.load(statBucket)">
              <option value="hour">小时</option>
              <option value="day">日</option>
              <option value="week">周</option>
              <option value="month">月</option>
            </select>
          </label>
          <span class="source-pill" :class="statistics.source.value">{{ statistics.source.value }}</span>
        </div>
      </header>
      <div v-if="statistics.data.value" class="stat-block">
        <p class="text-body">扫描事件 <strong>{{ statistics.data.value.scanned }}</strong> 条；按 <code>{{ statistics.data.value.dimension }}</code> 维度聚合。</p>
        <table class="ops-table">
          <thead><tr><th>桶</th><th>总数</th><th>分布</th></tr></thead>
          <tbody>
            <tr v-for="b in statistics.data.value.buckets" :key="b.bucket_key">
              <td><code>{{ b.bucket_key }}</code></td>
              <td>{{ b.total }}</td>
              <td>
                <span v-for="(v, k) in b.by_dimension" :key="k" class="status-pill">{{ k }}: {{ v }}</span>
              </td>
            </tr>
          </tbody>
        </table>
        <div class="totals-row">
          <strong>累计：</strong>
          <span v-for="t in statisticsTotalRow" :key="t.key" class="status-pill">{{ t.key }}: {{ t.value }}</span>
        </div>
      </div>
      <div v-else class="text-body text-zw-mute">等待装载……</div>
    </section>

    <!-- 异常 -->
    <section v-show="activePanel === 'anomaly'" class="panel">
      <header class="panel-head">
        <h2 class="panel-title">异常与督查</h2>
        <span class="source-pill" :class="anomaly.source.value">{{ anomaly.source.value }}</span>
      </header>
      <div v-if="anomaly.data.value && anomaly.data.value.anomalies.length">
        <p class="text-body">扫描事件 <strong>{{ anomaly.data.value.scanned }}</strong> 条；命中 <strong>{{ anomaly.data.value.anomalies.length }}</strong> 项异常。</p>
        <ul class="anom-list">
          <li v-for="(a, idx) in sortedAnomalies" :key="idx" :class="['anom-item', `severity-${a.severity}`]">
            <header>
              <span class="rule-tag">{{ a.rule }}</span>
              <span class="severity-tag">{{ a.severity }}</span>
              <span class="occ">{{ a.occurrence_count }} 次</span>
            </header>
            <p class="anom-summary">{{ a.summary }}</p>
            <p class="anom-actor">关注对象：<code>{{ a.actor }}</code><span v-if="a.skill_id"> · 操作 <code>{{ a.skill_id }}</code></span></p>
            <p class="anom-evidence">证据：
              <code v-for="rid in a.evidence_request_ids" :key="rid" class="evidence-rid">{{ rid }}</code>
            </p>
          </li>
        </ul>
      </div>
      <div v-else class="text-body text-zw-mute">当前窗口无异常。</div>
    </section>

    <!-- 追责 -->
    <section v-show="activePanel === 'accountability'" class="panel">
      <header class="panel-head">
        <h2 class="panel-title">追责链路</h2>
        <div class="panel-controls">
          <label>关注对象：
            <input v-model="accountActor" type="text" placeholder="user:gov:ROLE_*:名字" @change="accountability.load(accountActor)" />
          </label>
          <span class="source-pill" :class="accountability.source.value">{{ accountability.source.value }}</span>
        </div>
      </header>
      <div v-if="accountability.data.value && accountability.data.value.total > 0">
        <p class="text-body">关注对象 <code>{{ accountability.data.value.actor }}</code> 共 <strong>{{ accountability.data.value.total }}</strong> 条 denied 链。</p>
        <ul class="chain-list">
          <li v-for="chain in accountability.data.value.denied_chains" :key="chain.request_id" class="chain-item">
            <header>
              <code class="chain-rid">{{ chain.request_id }}</code>
              <span class="status-pill">{{ chain.skill_id }}</span>
              <time>{{ chain.denied_at }}</time>
            </header>
            <ol class="chain-events">
              <li v-for="(ev, i) in chain.events" :key="i">
                <span class="phase">{{ ev.phase }}</span>
                <time>{{ ev.occurred_at }}</time>
                <pre class="sanitized">{{ JSON.stringify(ev.sanitized_payload, null, 2) }}</pre>
              </li>
            </ol>
          </li>
        </ul>
      </div>
      <div v-else class="text-body text-zw-mute">该对象近期无 denied 链。</div>
    </section>

    <!-- 回放 -->
    <section v-show="activePanel === 'replay'" class="panel">
      <header class="panel-head">
        <h2 class="panel-title">审计链回放</h2>
        <div class="panel-controls">
          <label>请求编号：
            <input v-model="replayRequestId" type="text" @change="replay.load(replayRequestId)" />
          </label>
          <span class="source-pill" :class="replay.source.value">{{ replay.source.value }}</span>
        </div>
      </header>
      <div v-if="replay.data.value">
        <p class="text-body">链 <code>{{ replay.data.value.request_id }}</code> 共 <strong>{{ replay.data.value.items.length }}</strong> 个阶段。</p>
        <ol class="replay-list">
          <li v-for="(ev, i) in replay.data.value.items" :key="i" class="replay-item">
            <header>
              <span class="phase">{{ ev.phase }}</span>
              <time>{{ ev.occurred_at }}</time>
              <span class="status-pill">{{ ev.audit_class }}</span>
            </header>
            <p class="replay-actor"><code>{{ ev.actor }}</code> · <code>{{ ev.skill_id }}</code></p>
            <pre class="replay-payload">{{ JSON.stringify(ev.payload, null, 2) }}</pre>
          </li>
        </ol>
      </div>
      <div v-else class="text-body text-zw-mute">等待装载……</div>
    </section>

    <!-- 调查摘要助手 — 与原始证据并列，永不替代 -->
    <section class="panel assistant-panel">
      <header class="panel-head">
        <h2 class="panel-title">调查摘要助手 <span class="assistant-tag">AI 辅助</span></h2>
        <div class="panel-controls">
          <button type="button" class="gov-btn gov-btn-primary" @click="runSummary">
            就当前视图生成摘要
          </button>
          <span v-if="summary.source.value !== 'idle'" class="source-pill" :class="summary.source.value">{{ summary.source.value }}</span>
        </div>
      </header>
      <p class="assistant-disclaimer">
        助手摘要 <strong>不替代</strong> 上方原始审计证据；如出现 <code>sha1:...</code> 字段是脱敏后的稳定指纹，按原文保留不还原。
      </p>
      <div v-if="summary.data.value" class="assistant-result">
        <p class="assistant-summary">{{ summary.data.value.summary }}</p>
        <p class="assistant-meta">
          模型 <code>{{ summary.data.value.model }}</code> · 脱敏指纹 <code>{{ summary.data.value.sanitized_input_digest }}</code>
        </p>
      </div>
      <div v-else-if="summary.source.value === 'loading'" class="text-body text-zw-mute">正在生成……</div>
      <div v-else class="text-body text-zw-mute">点击上方按钮就当前视图生成摘要。</div>
    </section>
  </main>
</template>

<style scoped>
.page-shell { display: grid; gap: 16px; }
.hero-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.panel-tab-row { display: flex; gap: 8px; align-items: center; }
.panel-tabs { display: flex; gap: 8px; align-items: center; }
.panel-tab {
  background: var(--b-bg-subtle, #e8f2fc); color: var(--b-neutral-text, #1a1d21);
  border: 1px solid var(--b-border, #d4e2f4); padding: 6px 14px; border-radius: 6px;
  font-size: 13px; cursor: pointer;
}
.panel-tab.active { background: var(--b-primary, #006be6); color: #fff; border-color: var(--b-primary, #006be6); }
.refresh-btn { margin-left: auto; }
.panel-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 8px; }
.panel-controls { display: flex; gap: 12px; align-items: center; font-size: 13px; }
.panel-controls input, .panel-controls select {
  padding: 4px 8px; border: 1px solid var(--b-border, #d4e2f4); border-radius: 4px; font-size: 13px;
}
.source-pill {
  font-size: 12px; padding: 2px 8px; border-radius: 999px;
  background: var(--b-bg-subtle, #e8f2fc); color: var(--b-muted, #5c6370);
}
.source-pill.live { background: #d4f8e0; color: #155724; }
.source-pill.fixture { background: #fff3cd; color: #856404; }
.source-pill.loading { background: #cfe2ff; color: #084298; }
.ops-table { width: 100%; border-collapse: collapse; margin-top: 12px; }
.ops-table th, .ops-table td { padding: 10px 8px; text-align: left; font-size: 13px; border-bottom: 1px solid var(--b-border, #d4e2f4); }
.ops-table th { background: var(--b-bg-subtle, #e8f2fc); color: var(--b-muted, #5c6370); font-weight: 600; }
.status-pill { background: var(--b-bg-subtle, #e8f2fc); color: var(--b-primary, #006be6); font-size: 12px; padding: 2px 8px; border-radius: 999px; margin-right: 4px; display: inline-block; }
code { background: var(--b-bg-subtle, #e8f2fc); padding: 2px 6px; border-radius: 4px; font-size: 12px; }
.totals-row { margin-top: 12px; font-size: 13px; }
.anom-list { list-style: none; padding: 0; margin: 12px 0 0; display: grid; gap: 10px; }
.anom-item {
  padding: 12px; border-radius: 6px; background: #fff;
  border-left: 4px solid var(--b-border, #d4e2f4);
}
.anom-item.severity-high { border-left-color: #d9534f; }
.anom-item.severity-medium { border-left-color: #f0ad4e; }
.anom-item.severity-low { border-left-color: #5cb85c; }
.anom-item header { display: flex; gap: 8px; align-items: center; }
.rule-tag { background: var(--b-primary, #006be6); color: #fff; font-size: 11px; padding: 2px 6px; border-radius: 4px; }
.severity-tag { font-size: 11px; padding: 2px 6px; border-radius: 4px; background: var(--b-bg-subtle, #e8f2fc); color: var(--b-muted, #5c6370); text-transform: uppercase; }
.occ { margin-left: auto; font-size: 12px; color: var(--b-muted, #5c6370); }
.anom-summary { margin: 6px 0 4px; font-size: 13px; }
.anom-actor, .anom-evidence { margin: 2px 0; font-size: 12px; color: var(--b-muted, #5c6370); }
.evidence-rid { margin-right: 4px; }
.chain-list { list-style: none; padding: 0; margin: 12px 0 0; display: grid; gap: 12px; }
.chain-item { padding: 10px 12px; background: #fff; border-radius: 6px; border: 1px solid var(--b-border, #d4e2f4); }
.chain-item header { display: flex; gap: 8px; align-items: center; margin-bottom: 6px; font-size: 12px; }
.chain-rid { background: var(--b-bg-subtle, #e8f2fc); color: var(--b-primary, #006be6); }
.chain-events { list-style: decimal; margin: 0; padding-left: 18px; font-size: 12px; }
.chain-events li { margin: 4px 0; }
.phase { display: inline-block; font-weight: 600; min-width: 60px; }
.sanitized, .replay-payload {
  background: #f7f8fb; padding: 6px; border-radius: 4px;
  font-family: ui-monospace, "SF Mono", monospace; font-size: 11px;
  white-space: pre-wrap; word-break: break-all; margin: 4px 0 0;
}
.replay-list { list-style: none; padding: 0; margin: 12px 0 0; display: grid; gap: 10px; }
.replay-item { padding: 10px 12px; background: #fff; border-radius: 6px; border-left: 3px solid var(--b-primary, #006be6); }
.replay-item header { display: flex; gap: 8px; align-items: center; font-size: 12px; }
.replay-actor { margin: 4px 0 0; font-size: 12px; color: var(--b-muted, #5c6370); }
.assistant-panel { border-top: 2px solid var(--b-primary, #006be6); }
.assistant-tag { font-size: 11px; padding: 2px 6px; background: #fff3cd; color: #856404; border-radius: 4px; margin-left: 8px; }
.assistant-disclaimer { font-size: 12px; color: var(--b-muted, #5c6370); margin: 0 0 8px; }
.assistant-result { padding: 12px; background: var(--b-bg-subtle, #e8f2fc); border-radius: 6px; }
.assistant-summary { font-size: 13px; line-height: 1.6; margin: 0; }
.assistant-meta { font-size: 11px; color: var(--b-muted, #5c6370); margin: 6px 0 0; }
.gov-btn { padding: 5px 12px; border-radius: 6px; font-size: 12px; cursor: pointer; border: 1px solid transparent; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
</style>
