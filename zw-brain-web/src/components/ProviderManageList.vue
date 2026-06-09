<script setup lang="ts">
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import type { ProviderAssetRow } from '@/lib/providerProjection';

// 供数侧「目录 / 资源管理清单」共用表壳（T9）：两张清单页 90% 同构，差异只在 标题/链接/列配置/
// 数据源——抽这层展示组件消重，页面只剩"取 rows + 传列配置"。纯只读管理态、行内查看钻取。
interface Column {
  label: string;
  key: keyof ProviderAssetRow;
  /** 等宽 code 样式（目录代码等长标识）。 */
  mono?: boolean;
  /** 生命周期态 pill 样式。 */
  pill?: boolean;
}

defineProps<{
  title: string;
  meta: string;
  links: { label: string; href: string }[];
  columns: Column[];
  rows: ProviderAssetRow[];
  /** snapshot 是否已 live。 */
  loaded: boolean;
  /** 当前岗位是否有管理视图权限（无权=诚实提示，承「无权不可见」由路由/入口侧把关）。 */
  canView: boolean;
  emptyText: string;
  denyText: string;
  testid: string;
}>();
</script>

<template>
  <main class="focus-page">
    <section class="panel">
      <PageFocusHeader :title="title" :meta="meta" :links="links" />

      <p v-if="loaded && !canView" class="focus-empty">{{ denyText }}</p>
      <table v-else-if="loaded && rows.length" class="focus-table" :data-testid="testid">
        <thead>
          <tr>
            <th v-for="c in columns" :key="c.key">{{ c.label }}</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.id">
            <td v-for="c in columns" :key="c.key">
              <code v-if="c.mono" class="code-cell" :title="String(r[c.key] ?? '')">{{ r[c.key] }}</code>
              <span v-else-if="c.pill" class="status-pill">{{ r[c.key] }}</span>
              <template v-else>{{ r[c.key] }}</template>
            </td>
            <td>
              <a v-if="r.viewHref" :href="r.viewHref" class="row-link">查看</a>
              <span v-else class="muted">—</span>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else-if="loaded" class="focus-empty">{{ emptyText }}</p>
      <p v-else class="focus-empty">等待数据装载……</p>
    </section>
  </main>
</template>

<style scoped>
.code-cell { font-size: 12px; color: var(--b-muted, #5c6370); word-break: break-all; }
.row-link { color: var(--b-primary, #006be6); text-decoration: underline; font-size: 13px; }
.status-pill { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 12px; background: #eef3fb; color: var(--b-text, #1f2733); }
.muted { color: #9aa5b1; }
</style>
