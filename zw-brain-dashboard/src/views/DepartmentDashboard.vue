<!--
  部门版大屏模板（design baseline §7.7.3 第二种模板，Phase-0 placeholder）.
  Renders one department's intake / output / SLA against the brain-wide
  baseline. All data flows are GET-only via dashboard.summary_department.
-->
<template>
  <main class="department-dashboard" aria-label="部门版大屏">
    <header>
      <h1>政务大脑 · 部门版</h1>
      <p class="subtitle">Phase-0 placeholder — dashboard.summary_department</p>
    </header>
    <section class="department-meta">
      <div>部门：—</div>
      <div>统计周期：—</div>
    </section>
    <section class="metrics">
      <table>
        <thead>
          <tr><th>指标</th><th>本期</th><th>上期</th><th>同比</th></tr>
        </thead>
        <tbody>
          <tr><td>数据资源订阅数</td><td>—</td><td>—</td><td>—</td></tr>
          <tr><td>共享专区调用</td><td>—</td><td>—</td><td>—</td></tr>
          <tr><td>SLA 达标率</td><td>—</td><td>—</td><td>—</td></tr>
        </tbody>
      </table>
    </section>
  </main>
</template>

<script lang="ts">
export default { name: "DepartmentDashboard" };
</script>
