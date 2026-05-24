<script setup lang="ts">
import { computed } from 'vue';
import { useCapabilityPackages, useSnapshot } from '@/composables/useSnapshot';
import { invokeActionStub, pushToast } from '@/composables/useActionStub';
import DrillStrip from '@/components/DrillStrip.vue';
import NLAcceleratorPanel from '@/components/NLAcceleratorPanel.vue';
import type { StructuredAction } from '@/composables/useNLAccelerator';

const NL_PRESETS_B12 = [
  '未注册能力包',
  '近 7 天 IAM 失败',
  '看接入故障',
];

function consumeNLAction(action: StructuredAction) {
  // navigate kind 由 NLAcceleratorPanel 自身处理。
  // invoke 真调；filter/draft 先 toast 反馈，page-specific 注入留 E4 后端 land 后接线。
  if (action.kind === 'invoke' && action.target) {
    void invokeActionStub({ skillId: action.target, payload: action.payload, successTitle: action.label });
  } else if (action.kind === 'filter' || action.kind === 'draft') {
    pushToast({ kind: 'info', title: '已应用', detail: action.label });
  }
}

const pkgs = useCapabilityPackages();
const { source } = useSnapshot();
const items = computed(() =>
  pkgs.value.map((p) => {
    const it = p as Record<string, unknown>;
    return {
      id: String(it.id ?? it.slug ?? ''),
      name: String(it.name ?? it.label ?? ''),
      trust: String(it.trust_level ?? it.trust ?? ''),
      version: String(it.version ?? it.runtime_spec_version ?? ''),
    };
  })
);
const drillItems = computed(() => [
  { label: '身份治理', href: '#/integration-admin/iam-governance', hint: 'IAM 矩阵' },
  { label: '回到合规', href: '#/compliance-ops', hint: '事件追责' },
]);

async function review(id: string) {
  await invokeActionStub({
    skillId: 'capability.version.review',
    payload: { id },
    successTitle: '已提交审核结论',
    pendingBackend: 'E4 接入扩展中心 (e4/plan.yaml F5)',
  });
}
</script>

<template>
  <main class="page-shell">
    <header class="page-hero">
      <div class="hero-row">
        <div>
          <div class="page-kicker">B1.2 · 后台支撑面</div>
          <h1 class="page-hero-title">平台接入与扩展中心</h1>
          <p class="page-hero-subtitle">能力包审核注册、外部接入配置、暴露矩阵与租户策略；仅管理员。</p>
        </div>
        <NLAcceleratorPanel page-anchor="B1.2" :presets="NL_PRESETS_B12" @action="consumeNLAction" />
      </div>
    </header>

    <DrillStrip kicker="高频任务" :items="drillItems" />

    <section class="panel">
      <header>
        <h2 class="panel-title">能力包注册表</h2>
        <p class="panel-subtitle">F3 阶段：列表 + 审核 stub；§8.4 七步流水线 UI 化留 Wave 2</p>
      </header>
      <table v-if="source === 'live' && items.length" class="pkg-table">
        <thead><tr><th>编号</th><th>名称</th><th>版本</th><th>信任级</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="p in items" :key="p.id">
            <td><a :href="`#/integration-admin/package/${encodeURIComponent(p.id)}`"><code>{{ p.id }}</code></a></td>
            <td>{{ p.name || '—' }}</td>
            <td>{{ p.version || '—' }}</td>
            <td><span class="trust-pill">{{ p.trust || 'unknown' }}</span></td>
            <td class="actions">
              <button type="button" class="gov-btn gov-btn-primary" data-skill="capability.version.review" @click="review(p.id)">审核</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else-if="source === 'live'" class="text-body text-zw-mute">暂无注册能力包（默认角色 / 默认租户视图）。</div>
      <div v-else class="text-body text-zw-mute">等待 /api/snapshot 装载注册表数据。</div>
    </section>
  </main>
</template>

<style scoped>
.page-shell { display: grid; gap: 16px; }
.hero-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.pkg-table { width: 100%; border-collapse: collapse; margin-top: 12px; }
.pkg-table th, .pkg-table td { padding: 10px 8px; text-align: left; font-size: 13px; border-bottom: 1px solid var(--b-border, #d4e2f4); }
.pkg-table th { background: var(--b-bg-subtle, #e8f2fc); color: var(--b-muted, #5c6370); font-weight: 600; }
.pkg-table code { background: var(--b-bg-subtle, #e8f2fc); padding: 2px 6px; border-radius: 4px; }
.trust-pill { font-size: 12px; padding: 2px 8px; border-radius: 999px; background: var(--b-bg-subtle, #e8f2fc); color: var(--b-primary, #006be6); }
.actions { display: flex; gap: 6px; }
.gov-btn { padding: 4px 10px; border-radius: 6px; font-size: 12px; cursor: pointer; border: 1px solid transparent; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
</style>
