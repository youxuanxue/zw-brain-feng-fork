<script setup lang="ts">
import { computed } from 'vue';
import { formatDataSource } from '@/lib/auditDisplay';

const props = defineProps<{ source: string }>();

const label = computed(() => formatDataSource(props.source));
</script>

<template>
  <span v-if="label" class="data-source-badge" :class="`ds-${source}`">{{ label }}</span>
</template>

<style scoped>
.data-source-badge {
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 999px;
  font-weight: 600;
  white-space: nowrap;
}
.ds-live {
  background: #d4f8e0;
  color: #155724;
}
.ds-fixture {
  background: #fff3cd;
  color: #856404;
}
.ds-loading {
  background: #cfe2ff;
  color: #084298;
}
.ds-error {
  background: #f8d7da;
  color: #842029;
}
</style>
