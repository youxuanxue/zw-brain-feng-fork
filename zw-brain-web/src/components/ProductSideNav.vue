<script setup lang="ts">
import { computed } from 'vue';
import { RouterLink, useRoute } from 'vue-router';
import { activeShellKey, visibleShellNavByGroup } from '@/config/productShellNav';

const props = defineProps<{
  role: string;
}>();

const route = useRoute();
const groups = computed(() => visibleShellNavByGroup(props.role));
const active = computed(() => activeShellKey(route.path));
</script>

<template>
  <nav v-if="groups.length" class="side-nav" aria-label="主导航">
    <div v-for="g in groups" :key="g.group" class="side-nav-group">
      <p class="side-nav-group-label">{{ g.label }}</p>
      <RouterLink
        v-for="item in g.items"
        :key="item.key"
        :to="item.to"
        class="side-nav-item"
        :class="{ 'is-active': item.key === active }"
        :aria-current="item.key === active ? 'page' : undefined"
      >
        <span class="side-nav-item-label">{{ item.navLabel }}</span>
        <span class="side-nav-item-desc">{{ item.navDesc }}</span>
      </RouterLink>
    </div>
  </nav>
</template>

<style scoped>
.side-nav {
  position: sticky;
  top: 80px;
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 4px 0;
  /* 自身封顶可滚动：导航项再多也不溢出视口，点底部项不再把右侧标题顶走（字号/内边距保持原状）。 */
  max-height: calc(100vh - 96px);
  overflow-y: auto;
  overscroll-behavior: contain;
}
.side-nav-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.side-nav-group-label {
  margin: 0 0 4px 12px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--b-muted, #5c6370);
}
.side-nav-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 9px 10px;
  border-radius: 10px;
  border-left: 3px solid transparent;
  text-decoration: none;
  transition: background 120ms ease, border-color 120ms ease;
}
.side-nav-item:hover {
  background: var(--b-bg-subtle, #e8f2fc);
}
.side-nav-item.is-active {
  background: var(--b-bg-subtle, #e8f2fc);
  border-left-color: var(--b-primary, #006be6);
}
.side-nav-item-label {
  font-size: 16px;
  font-weight: 600;
  line-height: 1.4;
  color: var(--b-neutral-text, #1a1d21);
}
.side-nav-item.is-active .side-nav-item-label {
  color: var(--b-primary, #006be6);
}
.side-nav-item-desc {
  font-size: 12px;
  line-height: 1.45;
  color: var(--b-muted, #5c6370);
}

/* 窄屏：侧边栏退化为顶部横向滚动条，描述隐藏（保导航不挤压内容）。 */
@media (max-width: 960px) {
  .side-nav {
    position: static;
    flex-direction: row;
    flex-wrap: nowrap;
    gap: 8px;
    border-bottom: 1px solid var(--b-border, #d4e2f4);
    padding-bottom: 10px;
    margin-bottom: 12px;
    max-width: 100%;
    max-height: none;
    overflow-x: auto;
    overflow-y: hidden;
    -webkit-overflow-scrolling: touch;
  }
  .side-nav-group {
    flex-direction: row;
    flex: 0 0 auto;
    flex-wrap: nowrap;
    gap: 6px;
    align-items: center;
  }
  .side-nav-group-label {
    flex: 0 0 auto;
    margin: 0 6px 0 0;
  }
  .side-nav-item {
    flex: 0 0 auto;
    padding: 6px 12px;
    border-left: 0;
    border-bottom: 2px solid transparent;
    white-space: nowrap;
  }
  .side-nav-item.is-active {
    border-left: 0;
    border-bottom-color: var(--b-primary, #006be6);
  }
  .side-nav-item-desc {
    display: none;
  }
}
</style>
