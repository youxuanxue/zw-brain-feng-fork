<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailPanel from '@/components/DetailPanel.vue';
import DataSourceBadge from '@/components/DataSourceBadge.vue';
import { postSkill } from '@/composables/useApiClient';
import { mapDetailRows } from '@/lib/detailDisplay';
import { trustPillClass } from '@/lib/packageDisplay';
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
      <p v-else-if="error" class="focus-empty">{{ error }}</p>
    </section>
  </main>
</template>

<style scoped>
.trust-note { margin-top: 12px; font-size: 13px; }
</style>
