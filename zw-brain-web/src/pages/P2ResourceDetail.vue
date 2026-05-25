<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import { useResourceDetail } from '@/composables/useResourceDetail';
import { invokeActionStub } from '@/composables/useActionStub';
import { navigateToRequestDetail, resolveRequestIdFromAction } from '@/composables/useRequestNavigation';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailPanel from '@/components/DetailPanel.vue';
import DetailActions from '@/components/DetailActions.vue';
import { mapDetailRows } from '@/lib/detailDisplay';

const route = useRoute();
const id = computed(() => String(route.params.id ?? ''));
const { resource, source, loading, fetchError } = useResourceDetail(() => id.value);

const displayName = computed(() => {
  const r = resource.value;
  if (!r) return '';
  return String(r.name ?? r.title ?? '');
});

const rows = computed(() => {
  const r = resource.value;
  if (!r) return [];
  const out: { label: string; value: string }[] = [];
  if (r.provider) out.push({ label: '提供方', value: String(r.provider) });
  if (r.zone) out.push({ label: '归属专题', value: String(r.zone) });
  if (r.status) out.push({ label: '当前状态', value: String(r.status) });
  if (r.updatedAt) out.push({ label: '最近更新', value: String(r.updatedAt) });
  if (r.subscribers !== undefined) out.push({ label: '订阅量', value: String(r.subscribers) });
  if (r.coverage) out.push({ label: '字段覆盖', value: String(r.coverage) });
  if (r.approvalRate) out.push({ label: '审批通过率', value: String(r.approvalRate) });
  return mapDetailRows(out);
});

const fields = computed(() => (Array.isArray(resource.value?.fields) ? (resource.value!.fields as string[]) : []));
const explain = computed(() => (Array.isArray(resource.value?.explain) ? (resource.value!.explain as string[]) : []));

const headerTitle = computed(() => {
  if (resource.value) return displayName.value || id.value;
  if (loading.value) return '正在加载……';
  return id.value;
});
const headerMeta = computed(() => {
  if (resource.value && resource.value.desc) return String(resource.value.desc);
  if (fetchError.value) return `加载失败：${fetchError.value}`;
  if (source.value !== 'live') return '正在加载资源详情……';
  if (!resource.value) return '未找到该资源';
  return '';
});

async function apply() {
  const result = await invokeActionStub({
    skillId: 'request.create',
    payload: { resource_id: id.value },
    successTitle: '复用申请已起草',
    pendingBackend: 'E2 申请管理 (e2/plan.yaml F4)',
  });
  const requestId = resolveRequestIdFromAction(result);
  if (requestId) navigateToRequestDetail(requestId);
}
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/discovery">← 资源发现</a></nav>
    <section class="panel">
      <PageFocusHeader :title="headerTitle" :meta="headerMeta" />
      <DetailPanel v-if="rows.length" title="基本信息" :rows="rows" />
      <section v-if="fields.length" class="detail-block">
        <h2 class="detail-block-title">字段清单（前 12 项）</h2>
        <ul class="chip-list">
          <li v-for="f in fields.slice(0, 12)" :key="f">{{ f }}</li>
        </ul>
      </section>
      <section v-if="explain.length" class="detail-block">
        <h2 class="detail-block-title">复用提示</h2>
        <ul class="hint-list">
          <li v-for="e in explain" :key="e">{{ e }}</li>
        </ul>
      </section>
      <DetailActions>
        <button type="button" class="gov-btn gov-btn-primary" data-skill="request.create" @click="apply">发起复用申请</button>
        <a href="#/zones-pack" class="gov-btn gov-btn-secondary">看专题</a>
      </DetailActions>
    </section>
  </main>
</template>

<style scoped>
.chip-list { list-style: none; padding: 0; margin: 8px 0 0; display: flex; flex-wrap: wrap; gap: 6px; }
.chip-list li { font-size: 12px; padding: 2px 10px; background: var(--b-bg-page, #f2f7fd); border: 1px solid var(--b-border, #d4e2f4); border-radius: 999px; }
.hint-list { padding-left: 20px; margin: 8px 0 0; font-size: 14px; line-height: 1.6; }
.hint-list li { padding: 4px 0; }
</style>
