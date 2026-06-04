<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailPanel from '@/components/DetailPanel.vue';
import DataSourceBadge from '@/components/DataSourceBadge.vue';
import { postSkill } from '@/composables/useApiClient';
import { mapDetailRows } from '@/lib/detailDisplay';
import { trustPillClass } from '@/lib/packageDisplay';
import { PRODUCT_ROLE_LABELS } from '@/composables/useAuth';
import type { PanelSource } from '@/composables/usePackageLifecycle';

const route = useRoute();
const id = computed(() => String(route.params.id ?? ''));
const pkg = ref<Record<string, unknown> | null>(null);
const source = ref<PanelSource>('idle');
const error = ref<string | null>(null);

const TRUST_LABELS: Record<string, string> = {
  baseline: '基线（默认）',
  reviewed: '已审',
  restricted: '严管',
  revoked: '撤回',
};

// 消费面（5 投影）人话化——与 productShellNav / 暴露矩阵口径一致。
const SURFACE_LABELS: Record<string, string> = {
  webui: '业务页面',
  api: '接口调用',
  cli: '命令行',
  mcp: 'MCP',
  a2a: '智能体互联',
};

async function load() {
  source.value = 'loading';
  error.value = null;
  try {
    const payload = await postSkill<Record<string, unknown>>('package.view', {
      role: 'ROLE_BUSIAUDIT',
      tenant_id: 'sd-default',
      package_id: id.value,
    });
    pkg.value = payload;
    source.value = 'live';
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
    source.value = 'idle';
  }
}

onMounted(() => { void load(); });

const rows = computed(() => {
  const p = pkg.value;
  if (!p) return [];
  return mapDetailRows([
    { label: '编号', value: id.value },
    { label: '名称', value: String(p.name ?? '—') },
    { label: '状态', value: String(p.status ?? '—') },
    { label: '版本', value: String(p.version ?? '—') },
    {
      label: '内置信任级',
      value: TRUST_LABELS[String(p.trust_level ?? '')] ?? String(p.trust_level ?? '—'),
    },
    { label: '描述', value: String(p.description ?? p.summary ?? '—') },
  ]);
});

// 开放范围 = 这项能力被允许出现在哪些消费面、对哪个租户/角色开放。
// 全部取自 package.view 既有返回（compatibility/exposure + tenantPolicy），不另发请求、不改后端。
interface ScopeView {
  surfaces: string[];
  tenantId: string | null;
  policyStatus: string | null;
  roleCodes: string[];
}

const POLICY_STATUS_LABELS: Record<string, string> = {
  enabled: '已启用',
  disabled: '已停用',
};

const scope = computed<ScopeView | null>(() => {
  const p = pkg.value;
  if (!p) return null;
  const rawSurfaces = Array.isArray(p.compatibility)
    ? p.compatibility
    : Array.isArray(p.exposure)
      ? p.exposure
      : [];
  const tp = (p.tenantPolicy ?? null) as Record<string, unknown> | null;
  const policy = (tp?.policy ?? null) as Record<string, unknown> | null;
  const nestedRoleCodes = (policy?.tenantPolicy as Record<string, unknown> | undefined)?.role_codes;
  const rawRoleCodes = Array.isArray(nestedRoleCodes)
    ? nestedRoleCodes
    : Array.isArray(policy?.role_codes)
      ? (policy?.role_codes as unknown[])
      : [];
  return {
    surfaces: (rawSurfaces as unknown[]).map((s) => String(s)),
    tenantId: tp?.tenantId ? String(tp.tenantId) : p.tenantScope ? String(p.tenantScope) : null,
    policyStatus: tp?.policyStatus ? String(tp.policyStatus) : null,
    roleCodes: rawRoleCodes.map((r) => String(r)),
  };
});

const headerMeta = computed(() => {
  if (error.value) return error.value;
  if (source.value === 'loading') return '正在加载……';
  return String(pkg.value?.name ?? '能力包详情');
});
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/integration-admin">← 接入扩展中心</a></nav>
    <section class="panel">
      <PageFocusHeader :title="headerMeta" meta="能力包注册详情">
        <template #aside>
          <DataSourceBadge :source="source" />
        </template>
      </PageFocusHeader>
      <DetailPanel v-if="rows.length" title="基本信息" :rows="rows" />
      <p v-if="pkg?.trust_level" class="trust-note">
        内置信任级：
        <span :class="['trust-pill', trustPillClass(String(pkg.trust_level))]">
          {{ TRUST_LABELS[String(pkg.trust_level)] ?? pkg.trust_level }}
        </span>
      </p>

      <section v-if="scope" class="scope-card">
        <h2 class="scope-title">开放范围</h2>
        <p class="scope-hint">这项能力被允许出现在哪些环节、对谁开放——范围之外一律不可见、不可调用。</p>

        <div class="scope-block">
          <span class="scope-label">可用消费面</span>
          <template v-if="scope.surfaces.length">
            <span v-for="s in scope.surfaces" :key="s" class="scope-pill">{{ SURFACE_LABELS[s] ?? s }}</span>
          </template>
          <span v-else class="scope-empty">尚未开放任何消费面</span>
        </div>

        <div class="scope-block">
          <span class="scope-label">租户启用</span>
          <template v-if="scope.policyStatus">
            <span :class="['scope-pill', scope.policyStatus === 'enabled' ? 'scope-pill-on' : 'scope-pill-off']">
              {{ scope.tenantId || '本租户' }} · {{ POLICY_STATUS_LABELS[scope.policyStatus] ?? scope.policyStatus }}
            </span>
            <span v-for="r in scope.roleCodes" :key="r" class="scope-pill scope-pill-role">
              {{ PRODUCT_ROLE_LABELS[r] ?? r }}
            </span>
          </template>
          <span v-else class="scope-empty">尚未对任何租户启用</span>
        </div>
      </section>

      <p v-if="error" class="focus-empty">{{ error }}</p>
    </section>
  </main>
</template>

<style scoped>
.trust-note { margin-top: 12px; font-size: 13px; }
.scope-card {
  margin-top: 16px;
  padding: 14px 16px;
  background: #fff;
  border: 1px solid var(--b-border, #d4e2f4);
  border-radius: 8px;
}
.scope-title { margin: 0 0 4px; font-size: 15px; color: var(--b-neutral-text, #1a1d21); }
.scope-hint { margin: 0 0 12px; font-size: 13px; color: var(--b-muted, #5c6370); line-height: 1.6; }
.scope-block { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 8px 0; }
.scope-label {
  min-width: 76px;
  font-size: 13px;
  font-weight: 600;
  color: var(--b-muted, #5c6370);
}
.scope-pill {
  font-size: 12px;
  padding: 2px 10px;
  border-radius: 999px;
  background: var(--b-bg-subtle, #e8f2fc);
  color: var(--b-primary, #006be6);
  display: inline-block;
}
.scope-pill-on { background: #d4f8e0; color: #155724; }
.scope-pill-off { background: #f8d7da; color: #842029; }
.scope-pill-role { background: #fff; border: 1px solid var(--b-border, #d4e2f4); color: var(--b-neutral-text, #1a1d21); }
.scope-empty { font-size: 13px; color: var(--b-muted, #5c6370); }
</style>
