<script setup lang="ts">
import { computed, onMounted } from 'vue';
import { useGatewayRuntime } from '@/composables/useGatewayRuntime';
import { getProductRole } from '@/composables/useProductRole';
import { waitForAuthBootstrap } from '@/composables/useAuth';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DataSourceBadge from '@/components/DataSourceBadge.vue';
import { formatTime } from '@/lib/userLanguage';

// 服务调用监控（P8，Wave1-S3）：从「查审计」拆出的网关运行 / 服务调用只读面。
// 平台运维员保留服务调用监控（v5 服务调用日志 = 平台运维员 + 业务运营员）；
// 部门管理员 / 安全审计员保留只读。导航 + 后端 ops.service.report.query.execute 把守可见性，
// 无权角色看不到本导航项 → 进不来本页（无权 = 不可见）。
const currentRole = getProductRole();
const gateway = useGatewayRuntime();

onMounted(async () => {
  // 先等认证 bootstrap 完成：本页若在 bootstrap 落地前挂载，gateway.load 的
  // fetch 会卡在 bootstrap promise 上，徽标停在「加载中」。等齐再发请求。
  await waitForAuthBootstrap();
  await gateway.load(currentRole.value);
});

async function refresh(): Promise<void> {
  await gateway.load(currentRole.value);
}

// 网关运行状态：后端原始枚举 → 中文展示（段 24b 禁页面裸枚举）。
const GATEWAY_STATUS_LABELS: Record<string, string> = {
  online: '在线',
  warning: '降级',
  degraded: '降级',
  offline: '离线',
  unknown: '未知',
};
function gatewayStatusLabel(s: string): string {
  return GATEWAY_STATUS_LABELS[s] ?? '未知';
}
const gatewayRows = computed(() => gateway.data.value?.gateways ?? []);
const hasGatewaySignals = computed(() => gatewayRows.value.length > 0);
const gatewayCounts = computed(() => {
  let online = 0;
  let offline = 0;
  let degraded = 0;
  for (const g of gatewayRows.value) {
    if (g.status === 'online') online += 1;
    else if (g.status === 'offline') offline += 1;
    else degraded += 1;
  }
  return { online, degraded, offline };
});
const readinessCards = computed(() => [
  { title: '授权可追溯', body: '已签发的交付任务可查看授权要素、调用样例与审计边界。', href: '#/delivery-exchange' },
  { title: '审计可回放', body: '申请、审批、交付动作进入审计链路，便于客户现场追责与复盘。', href: '#/compliance-ops' },
  { title: '网关待接入', body: '客户网关心跳接入后，本页会自动显示实例在线、降级与离线状态。', href: '#/integration-admin' },
]);
</script>

<template>
  <main class="focus-page">
    <section class="panel panel-stack">
      <PageFocusHeader title="服务调用监控" meta="网关运行只读面" />

      <div class="focus-tab-row">
        <span class="focus-tab active" role="tab" aria-selected="true">网关运行</span>
        <button type="button" class="focus-tab refresh-btn" @click="refresh">刷新</button>
      </div>

      <section class="focus-section">
        <header class="focus-section-head">
          <h2 class="focus-section-title">网关运行</h2>
          <DataSourceBadge :source="gateway.source.value" />
        </header>
        <div v-if="hasGatewaySignals" class="gw-count-strip" role="group" aria-label="网关运行状态汇总">
          <span class="gw-count gw-count--online"><strong>{{ gatewayCounts.online }}</strong> 在线</span>
          <span class="gw-count gw-count--degraded"><strong>{{ gatewayCounts.degraded }}</strong> 降级</span>
          <span class="gw-count gw-count--offline"><strong>{{ gatewayCounts.offline }}</strong> 离线</span>
        </div>
        <table v-if="gatewayRows.length" class="focus-ops-table">
          <thead>
            <tr><th>网关实例</th><th>运行模式</th><th>状态</th><th>最近心跳</th><th>来源</th></tr>
          </thead>
          <tbody>
            <tr v-for="g in gatewayRows" :key="g.gateway_instance_id">
              <td><span class="tech-id">{{ g.gateway_instance_id }}</span></td>
              <!-- runtime_profile / source_ref 的 R12 判定延期下一轮（本轮只去裸时间戳）：
                   二者带 .tech-id 样式、可能是刻意保留的合法原始技术标识（同审计取证原文块的豁免精神），
                   留下一轮判定，避免误伤业务方要看的原始 ID。本轮不动。 -->
              <td>{{ g.runtime_profile }}</td>
              <td><span :class="['gw-status', `gw-status--${g.status}`]">{{ gatewayStatusLabel(g.status) }}</span></td>
              <td>{{ formatTime(g.last_reported_at) }}</td>
              <td><span class="tech-id">{{ g.source_ref }}</span></td>
            </tr>
          </tbody>
        </table>
        <p v-else-if="gateway.source.value === 'error'" class="focus-prose focus-prose--muted">数据暂不可用，请稍后重试。</p>
        <div v-else class="gw-ready">
          <p class="gw-ready-lead">客户网关心跳尚未接入，本页不编造运行数据；当前可先验收授权、审计与交付闭环。</p>
          <ul class="gw-ready-grid">
            <li v-for="card in readinessCards" :key="card.title" class="gw-ready-card">
              <h3>{{ card.title }}</h3>
              <p>{{ card.body }}</p>
              <a :href="card.href">查看</a>
            </li>
          </ul>
        </div>
      </section>
    </section>
  </main>
</template>

<style scoped>
.gw-count-strip { display: flex; gap: 10px; margin: 12px 0; flex-wrap: wrap; }
.gw-count { padding: 8px 14px; border-radius: 6px; font-size: 13px; background: var(--b-bg-subtle, #e8f2fc); color: var(--b-muted, #5c6370); }
.gw-count strong { font-size: 18px; margin-right: 4px; color: var(--b-neutral-text, #1a1d21); }
.gw-count--online { border-left: 3px solid #5cb85c; }
.gw-count--degraded { border-left: 3px solid #f0ad4e; }
.gw-count--offline { border-left: 3px solid #d9534f; }
.gw-status { font-size: 12px; padding: 2px 8px; border-radius: 4px; background: var(--b-bg-subtle, #e8f2fc); }
.gw-status--online { background: #e6f4ea; color: #1e7e34; }
.gw-status--warning, .gw-status--degraded { background: #fcf3e3; color: #8a6d3b; }
.gw-status--offline { background: #fdecea; color: #a02622; }
.gw-ready { display: grid; gap: 12px; margin-top: 12px; }
.gw-ready-lead { margin: 0; color: var(--b-muted, #5c6370); font-size: 13px; }
.gw-ready-grid { list-style: none; display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin: 0; padding: 0; }
.gw-ready-card { border: 1px solid var(--b-border, #d4e2f4); border-radius: 10px; padding: 12px; background: #fff; }
.gw-ready-card h3 { margin: 0 0 6px; font-size: 14px; color: var(--b-neutral-text, #1a1d21); }
.gw-ready-card p { margin: 0 0 10px; color: var(--b-muted, #5c6370); font-size: 12px; line-height: 1.5; }
.gw-ready-card a { color: var(--b-primary, #006be6); font-size: 13px; text-decoration: none; }
.gw-ready-card a:hover { text-decoration: underline; }
</style>
