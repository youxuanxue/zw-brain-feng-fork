<script setup lang="ts">
import { computed } from 'vue';
import { getProductRole } from '@/composables/useProductRole';
import { canPerformAction, filterByRouteAccess } from '@/lib/pageAccess';

export interface FocusLink {
  label: string;
  href: string;
  /**
   * 非空 → 渲染为禁用样式 + tooltip。用于「已立项未上线」入口在验收 walkthrough 中先以
   * disabled 形态可见。触发实施时直接删除该字段即可（不需要改组件）。详见 preflight-debt.md。
   */
  disabledReason?: string;
  /**
   * 可选：Action 级权限闸门 skill 槽位（如 'credential.issue'）。设置后，PageFocusHeader 会
   * 同时按 ACTION_ROLE_GATES 检查；当前 role 无权时**直接不渲染**（不是 disabled，也不是点击 403），
   * 兑现「无权 = 不可见」共性约束。
   *
   * 用法：在调用方 :links 中给需要写权限的入口标 requires，例如交付页「申请凭据」、提供方页「发布目录」。
   * 仅查询/浏览类入口不要设。
   */
  requires?: string;
}

const props = defineProps<{
  title: string;
  meta?: string;
  links?: FocusLink[];
}>();

const role = getProductRole();

// 单点过滤经由 pageAccess.filterByRouteAccess（同 P5Provider 待办卡 + 任何页内 nav），
// 调用方写死的 links 无权岗位直接看不到入口。
// 进一步：若 link 声明 requires action，且当前 role 不满足 ACTION_ROLE_GATES → 也不渲染。
const visibleLinks = computed<FocusLink[]>(() => {
  const routeFiltered = filterByRouteAccess(props.links ?? [], (l) => l.href, role.value);
  return routeFiltered.filter((l) => !l.requires || canPerformAction(l.requires, role.value));
});
</script>

<template>
  <header class="focus-head">
    <div class="focus-head-row">
      <div class="focus-head-main">
        <h1 class="focus-title">{{ title }}</h1>
        <p v-if="meta" class="focus-meta">{{ meta }}</p>
      </div>
      <nav v-if="visibleLinks.length" class="focus-links" aria-label="相关入口">
        <template v-for="(link, i) in visibleLinks" :key="link.href + link.label">
          <span v-if="i > 0" class="focus-sep" aria-hidden="true">·</span>
          <span
            v-if="link.disabledReason"
            class="focus-link-disabled"
            :title="link.disabledReason"
            :aria-disabled="true"
          >{{ link.label }}</span>
          <a v-else :href="link.href">{{ link.label }}</a>
        </template>
      </nav>
      <div v-if="$slots.aside" class="focus-aside">
        <slot name="aside" />
      </div>
    </div>
    <div v-if="$slots.default" class="focus-extra">
      <slot />
    </div>
  </header>
</template>

<style scoped>
.focus-head {
  padding-bottom: 12px;
  border-bottom: 1px solid var(--b-border, #d4e2f4);
  margin-bottom: 4px;
}
.focus-head-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px 20px;
  flex-wrap: wrap;
}
.focus-title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  line-height: 1.35;
  color: var(--b-neutral-text, #1a1d21);
}
.focus-meta {
  margin: 4px 0 0;
  font-size: 13px;
  line-height: 1.45;
  color: var(--b-muted, #5c6370);
}
.focus-links {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  font-size: 13px;
}
.focus-links a {
  color: var(--b-primary, #006be6);
  text-decoration: none;
  font-weight: 500;
}
.focus-links a:hover {
  text-decoration: underline;
}
.focus-link-disabled {
  color: var(--b-muted-soft, #9aa3b2);
  cursor: not-allowed;
  font-weight: 500;
}
.focus-sep {
  color: var(--b-muted-soft, #6f7786);
}
.focus-aside {
  flex-shrink: 0;
}
.focus-extra {
  width: 100%;
  margin-top: 10px;
}
</style>
