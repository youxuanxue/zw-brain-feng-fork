<script setup lang="ts">
import { ref } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailActions from '@/components/DetailActions.vue';
import { invokeActionStub } from '@/composables/useActionStub';

const title = ref('');
const targetId = ref('');
const basis = ref('字段描述与底册不一致');
const creating = ref(false);

async function createObjection() {
  if (!title.value.trim() || !targetId.value.trim()) return;
  creating.value = true;
  try {
    const result = await invokeActionStub({
      skillId: 'objection.case.create',
      payload: {
        objection_kind: 'catalog_quality',
        target_type: 'catalog',
        target_id: targetId.value.trim(),
        title: title.value.trim(),
        complainant_org_id: 'U_ORGAN_OPERATER',
        provider_org_id: 'U_PROVIDER_DEMO',
        basis_text: basis.value.trim(),
        evidence: [{ evidence_type: 'catalog', content_json: { source: 'p3-ui' } }],
      },
      successTitle: '异议已创建',
      refreshSnapshotAfter: true,
    });
    const data = result.data as Record<string, unknown> | undefined;
    const inner = (data?.result ?? data) as Record<string, unknown> | undefined;
    const newId = String(inner?.id ?? '');
    if (newId) window.location.hash = `#/request-flow/objection/${newId}`;
  } finally {
    creating.value = false;
  }
}
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/request-flow/objection">← 我的异议</a></nav>
    <section class="panel">
      <PageFocusHeader title="发起异议" meta="针对目录字段或资源质量问题提交异议" />
      <div class="form-grid">
        <label for="title">异议标题</label>
        <input id="title" v-model="title" placeholder="例如：字段描述与底册不一致" />
        <label for="target">目录/资源编号</label>
        <input id="target" v-model="targetId" placeholder="catalog 或 resource 编号" />
        <label for="basis">异议依据</label>
        <textarea id="basis" v-model="basis" rows="4" />
      </div>
      <DetailActions>
        <button
          type="button"
          class="gov-btn gov-btn-primary"
          :disabled="creating || !title.trim() || !targetId.trim()"
          @click="createObjection"
        >
          创建异议
        </button>
      </DetailActions>
    </section>
  </main>
</template>

<style scoped>
.form-grid { display: grid; gap: 8px; max-width: 560px; margin-bottom: 12px; }
label { font-size: 13px; color: var(--b-muted, #5c6370); }
input, textarea { padding: 8px 10px; border: 1px solid var(--b-border, #d4e2f4); border-radius: 6px; font-size: 14px; }
.gov-btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid transparent; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
</style>
