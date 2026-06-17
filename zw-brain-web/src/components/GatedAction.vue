<script setup lang="ts">
import { computed } from 'vue';
import { canPerformAction } from '@/lib/pageAccess';

// 行内 CTA 的「无权 = 不可见」原语：仅当当前岗位对 gate 有权时渲染默认插槽，
// 否则什么都不渲染。行内决策面不经路由守卫，按钮必须靠它自门控（不再「看得到 → 点击 403」）。
const props = defineProps<{ gate: string; role: string }>();

const allowed = computed(() => canPerformAction(props.gate, props.role));
</script>

<template>
  <slot v-if="allowed" />
</template>
