<script setup lang="ts">
export interface FocusLink {
  label: string;
  href: string;
}

defineProps<{
  title: string;
  meta?: string;
  links?: FocusLink[];
}>();
</script>

<template>
  <header class="focus-head">
    <div class="focus-head-row">
      <div class="focus-head-main">
        <h1 class="focus-title">{{ title }}</h1>
        <p v-if="meta" class="focus-meta">{{ meta }}</p>
      </div>
      <nav v-if="links?.length" class="focus-links" aria-label="相关入口">
        <template v-for="(link, i) in links" :key="link.href + link.label">
          <span v-if="i > 0" class="focus-sep" aria-hidden="true">·</span>
          <a :href="link.href">{{ link.label }}</a>
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
