<script setup lang="ts">
import { computed, ref } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailPanel from '@/components/DetailPanel.vue';
import DetailActions from '@/components/DetailActions.vue';
import { useProvider, useSnapshot } from '@/composables/useSnapshot';
import { invokeActionStub } from '@/composables/useActionStub';
import { mapDetailRows } from '@/lib/detailDisplay';
import { resourceCodeForApiService } from '@/lib/providerActionPayload';

const provider = useProvider();
const { source } = useSnapshot();
const selectedId = ref('');

const services = computed(() => {
  const list = (provider.value.services as unknown[] | undefined) ?? [];
  return list.map((s) => {
    const it = s as Record<string, unknown>;
    return {
      id: String(it.id ?? ''),
      name: String(it.name ?? ''),
      status: String(it.status ?? ''),
      qps: String(it.qps ?? '—'),
      note: String(it.note ?? ''),
    };
  });
});

const catalogApis = computed(() => {
  const list = (provider.value.catalog_items as unknown[] | undefined) ?? [];
  return list
    .map((c) => c as Record<string, unknown>)
    .filter((c) => String(c.item_kind ?? '').includes('api'))
    .map((c) => ({
      id: String(c.item_code ?? c.resource_code ?? ''),
      name: String(c.title ?? c.item_code ?? ''),
    }));
});

const selected = computed(
  () => services.value.find((s) => s.id === selectedId.value) ?? services.value[0] ?? null,
);

const previewRows = computed(() => {
  const s = selected.value;
  if (!s) return [];
  return mapDetailRows([
    { label: '服务名称', value: s.name },
    { label: '运行状态', value: s.status || '—' },
    { label: '当前 QPS', value: s.qps },
    { label: '说明', value: s.note || '—' },
  ]);
});

const headerMeta = computed(() => {
  if (source.value !== 'live') return '正在加载……';
  const n = services.value.length;
  return n ? `${n} 个可服务化 API · ${catalogApis.value.length} 个目录 API 分组` : '暂无 API 服务数据';
});

async function submitReview() {
  if (!selected.value) return;
  const resourceCode = resourceCodeForApiService(selected.value.id, provider.value as Record<string, unknown>);
  await invokeActionStub({
    skillId: 'resource.api.submit_review',
    payload: { resource_code: resourceCode },
    successTitle: '已提交 API 服务化审核',
  });
}

async function testEndpoint() {
  if (!selected.value) return;
  const resourceCode = resourceCodeForApiService(selected.value.id, provider.value as Record<string, unknown>);
  await invokeActionStub({
    skillId: 'resource.api.test',
    payload: {
      resource_code: resourceCode,
      test_result: 'passed',
      evidence_json: { probe: 'webui-wizard', service_id: selected.value.id },
    },
    successTitle: '连通性探测已登记',
  });
}
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/provider">← 提供方管理</a></nav>
    <section class="panel">
      <PageFocusHeader
        title="API 服务化向导"
        :meta="headerMeta"
        :links="[{ label: '质量规则向导', href: '#/provider/wizard/quality-rule' }]"
      />

      <template v-if="source === 'live' && services.length">
        <label class="field-label">选择待服务化 API</label>
        <select v-model="selectedId" class="gov-select">
          <option value="" disabled>请选择服务</option>
          <option v-for="s in services" :key="s.id" :value="s.id">{{ s.name }}（{{ s.status }}）</option>
        </select>
        <DetailPanel title="服务预览" :rows="previewRows" />
        <DetailActions>
          <button type="button" class="gov-btn gov-btn-secondary" @click="testEndpoint">探测连通性</button>
          <button type="button" class="gov-btn gov-btn-primary" @click="submitReview">提交服务化审核</button>
        </DetailActions>
      </template>
      <p v-else-if="source === 'live'" class="focus-empty">暂无 API 服务条目。</p>
      <p v-else class="focus-empty">等待数据装载……</p>
    </section>
  </main>
</template>

<style scoped>
.field-label { display: block; font-size: 13px; margin-bottom: 6px; color: var(--b-muted, #5c6370); }
.gov-select { width: 100%; max-width: 480px; padding: 6px 10px; margin-bottom: 12px; border-radius: 6px; border: 1px solid var(--b-border, #d4e2f4); }
.gov-btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid transparent; margin-right: 8px; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-secondary { background: #fff; border-color: var(--b-border, #d4e2f4); }
</style>
