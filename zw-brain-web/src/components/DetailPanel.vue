<script setup lang="ts">
defineProps<{
  title: string;
  subtitle?: string;
  rows: { label: string; value: string; state?: string; source?: string }[];
}>();
</script>

<template>
  <section class="panel">
    <header>
      <h2 class="panel-title">{{ title }}</h2>
      <p v-if="subtitle" class="panel-subtitle">{{ subtitle }}</p>
    </header>
    <dl class="detail-list">
      <template v-for="row in rows" :key="row.label">
        <dt>{{ row.label }}</dt>
        <dd>
          <span class="value">{{ row.value || '—' }}</span>
          <span v-if="row.state" class="state">{{ row.state }}</span>
          <span v-if="row.source" class="source">来源 · {{ row.source }}</span>
        </dd>
      </template>
    </dl>
  </section>
</template>

<style scoped>
.detail-list { display: grid; grid-template-columns: minmax(120px, 200px) 1fr; gap: 8px 16px; margin: 12px 0 0; }
.detail-list dt { font-size: 13px; color: var(--b-muted, #5c6370); padding: 6px 0; }
.detail-list dd { font-size: 14px; color: var(--b-neutral-text, #1a1d21); padding: 6px 0; margin: 0; border-bottom: 1px dashed var(--b-border, #d4e2f4); display: flex; flex-wrap: wrap; gap: 8px; }
.detail-list dd:last-of-type { border-bottom: 0; }
.value { font-weight: 500; }
.state { font-size: 12px; padding: 2px 8px; border-radius: 999px; background: var(--b-bg-subtle, #e8f2fc); color: var(--b-primary, #006be6); }
.source { font-size: 12px; color: var(--b-muted, #5c6370); }
</style>
