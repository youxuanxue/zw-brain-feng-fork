<script setup lang="ts">
import type { DetailRow } from '@/lib/detailDisplay';
import { statusToneForRow } from '@/lib/detailDisplay';

defineProps<{
  title?: string;
  subtitle?: string;
  rows: DetailRow[];
}>();
</script>

<template>
  <section class="detail-block">
    <header v-if="title" class="detail-block-head">
      <h2 class="detail-block-title">{{ title }}</h2>
      <p v-if="subtitle" class="detail-block-sub">{{ subtitle }}</p>
    </header>
    <dl class="detail-list">
      <template v-for="row in rows" :key="row.label">
        <dt>{{ row.label }}</dt>
        <dd>
          <span
            v-if="row.kind === 'status'"
            class="status-pill"
            :class="statusToneForRow(row)"
          >{{ row.value }}</span>
          <template v-else-if="row.kind === 'actor'">
            <span class="detail-value">{{ row.value || '—' }}</span>
            <span v-if="row.raw" class="tech-id detail-raw">{{ row.raw }}</span>
          </template>
          <span v-else-if="row.kind === 'tech'" class="tech-id">{{ row.value || '—' }}</span>
          <a v-else-if="row.href" :href="row.href" class="detail-link">{{ row.value || '—' }}</a>
          <span v-else class="detail-value">{{ row.value || '—' }}</span>
          <span v-if="row.state" class="detail-meta-pill">{{ row.state }}</span>
          <span v-if="row.source" class="detail-meta">来源 · {{ row.source }}</span>
        </dd>
      </template>
    </dl>
  </section>
</template>

<style scoped>
.detail-link { color: var(--b-primary, #006be6); text-decoration: none; }
.detail-link:hover { text-decoration: underline; }
</style>
