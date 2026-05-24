<script setup lang="ts">
import { useRoute } from 'vue-router';

const route = useRoute();
</script>

<template>
  <main class="placeholder">
    <header class="placeholder-hero">
      <div class="placeholder-tag">{{ String(route.meta.page ?? '辅助页') }}</div>
      <h1>{{ String(route.meta.title ?? route.path) }}</h1>
      <p>该页面正在建设中。完成后将自动从这里接入真实数据并取代当前提示。</p>
    </header>
    <section class="placeholder-meta">
      <div><strong>当前路径：</strong> <code>#{{ route.path }}</code></div>
      <div><a href="#/workbench">回到工作台</a></div>
    </section>
  </main>
</template>

<style scoped>
.placeholder {
  max-width: 920px;
  margin: 48px auto;
  padding: 0 24px;
  font-family: 'Microsoft YaHei', 'PingFang SC', 'Noto Sans SC', system-ui, sans-serif;
}
.placeholder-hero {
  border: 1px solid #d4e2f4;
  border-radius: 12px;
  padding: 32px;
  background: linear-gradient(180deg, #ffffff 0%, #f7fbff 100%);
}
.placeholder-tag {
  display: inline-block;
  padding: 4px 12px;
  background: #006be6;
  color: #fff;
  border-radius: 999px;
  font-size: 13px;
  margin-bottom: 12px;
}
.placeholder-hero h1 {
  font-size: 24px;
  margin: 0 0 12px;
  color: #1a1d21;
}
.placeholder-hero p {
  font-size: 14px;
  color: #5c6370;
  line-height: 1.6;
  margin: 0;
}
.placeholder-meta {
  margin-top: 24px;
  display: grid;
  gap: 12px;
  font-size: 14px;
  color: #1a1d21;
}
.placeholder-meta a {
  color: #006be6;
  text-decoration: none;
}
.placeholder-meta a:hover {
  text-decoration: underline;
}
.placeholder-meta code {
  background: #e8f2fc;
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'JetBrains Mono', 'SFMono-Regular', Consolas, monospace;
}
</style>
