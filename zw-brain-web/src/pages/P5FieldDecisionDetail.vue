<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import { invokeActionStub } from '@/composables/useActionStub';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailPanel from '@/components/DetailPanel.vue';
import DetailActions from '@/components/DetailActions.vue';
import { mapDetailRows } from '@/lib/detailDisplay';

const route = useRoute();
const id = computed(() => String(route.params.id ?? ''));

const rows = computed(() =>
  mapDetailRows([
    { label: '裁决编号', value: id.value },
    { label: '范围', value: '山东省 sd-default' },
    { label: '处理时限', value: '5 个工作日' },
  ])
);

async function commit(decision: 'approve' | 'reject') {
  await invokeActionStub({
    skillId: 'catalog.entry.reverse_draft.confirm',
    payload: { id: id.value, decision },
    successTitle: decision === 'approve' ? '已通过' : '已驳回',
    pendingBackend: 'E4 提供方治理 (e4/plan.yaml F2)',
  });
}
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/provider/inbox/field-decision">← 字段裁决收件箱</a></nav>
    <section class="panel">
      <PageFocusHeader :title="`裁决 ${id}`" meta="提交后进入审计链，不可静默撤销" />
      <DetailPanel title="基本信息" :rows="rows" />
      <DetailActions>
        <button type="button" class="gov-btn gov-btn-primary" @click="commit('approve')">通过裁决</button>
        <button type="button" class="gov-btn gov-btn-danger" @click="commit('reject')">驳回</button>
      </DetailActions>
    </section>
  </main>
</template>
