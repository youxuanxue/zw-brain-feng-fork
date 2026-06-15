<script setup lang="ts">
import { ref } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import PhaseTrack from '@/components/PhaseTrack.vue';
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

withDefaults(
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
    /** 当前岗位是否可执行行内动作（C：草稿续编/提交审核）；false 时行内动作不渲染（无权=不可见）。 */
    canAct?: boolean;
  }>(),
  { canAct: false },
);

// C：行内动作按钮（actionId）点击 → 冒泡给页面承接调能力（href 类直接 <a> 跳转，不冒泡）。
const emit = defineEmits<{ (e: 'row-action', payload: { actionId: string; row: ProviderAssetRow }): void }>();

// F：办理进度脊柱默认收起，点「办理进度」展开 PhaseTrack（一次只展开一行，避免长表喧闹）。
const openTimelineId = ref('');
function toggleTimeline(id: string) {
  openTimelineId.value = openTimelineId.value === id ? '' : id;
}
function hasTimeline(r: ProviderAssetRow): boolean {
  return Array.isArray(r.timeline) && r.timeline.length > 0;
}
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
          <template v-for="r in rows" :key="r.id">
          <tr>
            <td v-for="c in columns" :key="c.key">
              <code v-if="c.mono" class="code-cell" :title="String(r[c.key] ?? '')">{{ r[c.key] }}</code>
              <template v-else-if="c.pill">
                <span class="status-pill">{{ r[c.key] }}</span>
                <!-- D57⑨/R-10：审核驳回理由随生命周期态回显（提交方整改依据，无则不渲染）。 -->
                <span v-if="r.statusNote" class="status-note" data-testid="row-status-note">{{ r.statusNote }}</span>
              </template>
              <template v-else>{{ r[c.key] }}</template>
            </td>
            <td class="row-ops">
              <!-- F：办理进度脊柱（供数侧「卡在谁桌上」）。有 timeline 才出按钮；支线态无 stepper。 -->
              <button
                v-if="hasTimeline(r)"
                type="button"
                class="row-action-btn"
                data-testid="row-timeline-toggle"
                @click="toggleTimeline(r.id)"
              >{{ openTimelineId === r.id ? '收起进度' : '办理进度' }}</button>
              <a v-if="r.viewHref" :href="r.viewHref" class="row-link">查看</a>
              <!-- C：草稿行内动作（仅有权岗位渲染）。href 类直接跳转续编向导；actionId 类点击调能力。 -->
              <template v-if="canAct && r.actions && r.actions.length">
                <a v-for="a in r.actions.filter((x) => x.href)" :key="a.label" :href="a.href" class="row-link">{{ a.label }}</a>
                <button
                  v-for="a in r.actions.filter((x) => x.actionId)"
                  :key="a.label"
                  type="button"
                  class="row-action-btn"
                  :class="{ danger: a.danger }"
                  @click="emit('row-action', { actionId: a.actionId as string, row: r })"
                >{{ a.label }}</button>
              </template>
              <span v-if="!r.viewHref && !hasTimeline(r) && !(canAct && r.actions && r.actions.length)" class="muted">—</span>
            </td>
          </tr>
          <!-- F：展开行——PhaseTrack 竖向脊柱（卡在谁桌上）。支线态（驳回/退役）走 lifecycleNote 诚实标注。 -->
          <tr v-if="openTimelineId === r.id && hasTimeline(r)" class="timeline-row">
            <td :colspan="columns.length + 1">
              <div class="timeline-wrap" data-testid="row-timeline-track">
                <PhaseTrack :steps="r.timeline ?? []" :aria-label="`${r.name} 办理进度`" />
                <p v-if="r.lifecycleNote" class="timeline-note">当前：{{ r.lifecycleNote }}</p>
              </div>
            </td>
          </tr>
          </template>
        </tbody>
      </table>
      <p v-else-if="loaded" class="focus-empty">{{ emptyText }}</p>
      <p v-else class="focus-empty">等待数据装载……</p>
    </section>
  </main>
</template>

<style scoped>
.code-cell { font-size: 12px; color: var(--b-muted, #5c6370); word-break: break-all; }
.row-ops { white-space: nowrap; }
.row-link { color: var(--b-primary, #006be6); text-decoration: underline; font-size: 13px; margin-right: 10px; }
.row-action-btn { background: none; border: 0; padding: 0; margin-right: 10px; color: var(--b-primary, #006be6); cursor: pointer; font-size: 13px; text-decoration: underline; }
.row-action-btn.danger { color: #c0392b; }
.status-pill { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 12px; background: #eef3fb; color: var(--b-text, #1f2733); }
.status-note { display: block; margin-top: 4px; font-size: 12px; color: #b42318; }
.muted { color: #9aa5b1; }
.timeline-row td { background: #f6f9fe; padding: 10px 14px; }
.timeline-wrap { padding: 4px 0; }
.timeline-note { margin: 4px 0 0; font-size: 12px; color: var(--b-muted, #5c6370); }
</style>
