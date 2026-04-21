<!--
  资源池版大屏模板（design baseline §7.7.3 第三种模板，Phase-0 placeholder）.
  Surface for the K11 共享专区 — subscriptions / utilization / overdue items.
  Read-only by construction.
-->
<template>
  <main class="resource-pool-dashboard" aria-label="资源池版大屏">
    <header>
      <h1>政务大脑 · 共享专区</h1>
      <p class="subtitle">Phase-0 placeholder — dashboard.list_resource_pool</p>
    </header>
    <section class="filters">
      <label>主题域：<span>—</span></label>
      <label>订阅状态：<span>—</span></label>
    </section>
    <section class="resource-grid">
      <p>资源卡片网格占位。Phase-1 起接入 dashboard.list_resource_pool。</p>
    </section>
  </main>
</template>

<script lang="ts">
export default { name: "ResourcePoolDashboard" };
</script>
