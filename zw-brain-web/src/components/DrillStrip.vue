<script setup lang="ts">
defineProps<{
  kicker?: string;
  items: { label: string; href: string; hint?: string }[];
}>();
</script>

<template>
  <section class="drill-strip" role="region" aria-label="快捷入口">
    <div v-if="kicker" class="drill-kicker">{{ kicker }}</div>
    <div v-if="!items.length" class="drill-empty">暂无快捷入口</div>
    <div v-else class="drill-grid">
      <a v-for="i in items" :key="i.href + i.label" :href="i.href" class="drill-card">
        <strong>{{ i.label }}</strong>
        <em v-if="i.hint">{{ i.hint }}</em>
      </a>
    </div>
  </section>
</template>

<style scoped>
.drill-strip {
  border: 1px solid var(--b-border, #d4e2f4);
  border-radius: 12px;
  padding: 16px;
  background: #fff;
}
.drill-kicker { font-size: 13px; color: var(--b-muted, #5c6370); margin-bottom: 8px; }
.drill-empty { font-size: 13px; color: var(--b-muted, #5c6370); }
.drill-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px;
}
.drill-card {
  display: block; padding: 12px; border: 1px solid var(--b-border, #d4e2f4); border-radius: 8px;
  text-decoration: none; color: inherit; background: var(--b-bg-page, #f2f7fd);
}
.drill-card:hover { background: var(--b-bg-subtle, #e8f2fc); border-color: var(--b-primary, #006be6); }
.drill-card strong { display: block; font-size: 14px; }
.drill-card em { display: block; font-style: normal; font-size: 12px; color: var(--b-muted, #5c6370); margin-top: 4px; }
</style>
