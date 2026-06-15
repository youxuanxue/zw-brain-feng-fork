<script setup lang="ts">
// J1 办理进度脊柱（竖向、左侧导轨自上而下读「卡在谁桌上」）。
// 单一事实源 = 后端 status_timeline；申请人/审批人/交付三页共用本组件，不在前端重派生。
// steps 由后端现算（stage/status/label/holder）；holder 仅当前段非空（在谁桌上）。
import { formatTodoStatus } from '@/lib/statusLabels';

interface TimelineStep {
  stage: string;
  status: string;
  label: string;
  holder?: string;
}

defineProps<{ steps: TimelineStep[]; ariaLabel?: string }>();

function stepClass(status: string): string {
  if (status === 'done') return 'phase-step phase-step-done';
  if (status === 'current') return 'phase-step phase-step-current';
  return 'phase-step';
}
</script>

<template>
  <div v-if="steps.length" class="phase-track-vertical" :aria-label="ariaLabel ?? '办理进度'">
    <div v-for="(step, i) in steps" :key="i" :class="stepClass(step.status)">
      <span class="phase-dot">{{ i + 1 }}</span>
      <span class="phase-step-body">
        <span class="phase-stage">{{ step.stage }}</span>
        <span class="phase-label">{{ formatTodoStatus(step.label) }}</span>
        <span v-if="step.holder" class="phase-holder">在 {{ step.holder }}</span>
      </span>
    </div>
  </div>
</template>

<style scoped>
.phase-track-vertical { display: flex; flex-direction: column; gap: 0; margin: 4px 0 16px; padding-left: 18px; border-left: 2px solid var(--b-border, #d4e2f4); }
.phase-step { display: flex; align-items: flex-start; gap: 10px; padding: 7px 0; color: var(--b-muted, #5c6370); }
.phase-step-current { color: var(--b-primary, #006be6); }
.phase-step-current .phase-stage { font-weight: 600; }
.phase-step-done { color: #2d6a2d; }
.phase-dot { display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px; border-radius: 50%; background: #9aa3b2; color: #fff; font-size: 10px; font-weight: 700; flex: 0 0 auto; margin-left: -28px; }
.phase-step-current .phase-dot { background: var(--b-primary, #006be6); }
.phase-step-done .phase-dot { background: #3d8b40; }
.phase-step-body { display: flex; flex-direction: column; line-height: 1.4; }
.phase-stage { font-size: 13px; }
.phase-label { font-size: 12px; color: var(--b-muted, #5c6370); }
.phase-holder { font-size: 12px; color: var(--b-primary, #006be6); margin-top: 1px; }
</style>
