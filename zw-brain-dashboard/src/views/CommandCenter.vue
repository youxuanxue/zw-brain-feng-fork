<!--
  指挥中心模板（design baseline §7.7.3 第一种模板，Phase-0 placeholder）.
  Once a framework is chosen in Phase-0 PoC the <script setup> block will
  bind real reactive state; for now this is a static skeleton consumed
  only by dashboard-readonly drift detection.
-->
<template>
  <main class="command-center" aria-label="指挥中心大屏">
    <header>
      <h1>政务大脑 · 指挥中心</h1>
      <p class="subtitle">Phase-0 placeholder — 真实数据接入后由 dashboard.render_command_center Skill 提供</p>
    </header>
    <section class="kpi-grid">
      <article class="kpi-card">在网部门：—</article>
      <article class="kpi-card">日均交换：—</article>
      <article class="kpi-card">告警事件：—</article>
      <article class="kpi-card">区块链锚定：—</article>
    </section>
    <section class="chart-region" aria-label="主图区">
      <p>图表占位（ECharts vs vega-lite 的选型延后到 Phase-0 PoC，D19）。</p>
    </section>
  </main>
</template>

<script lang="ts">
// Read-only data fetch will plug in after framework choice.
// import { queryDashboardSkill } from "../api/client";
// const summary = await queryDashboardSkill<unknown>("dashboard.render_command_center");
export default { name: "CommandCenter" };
</script>
