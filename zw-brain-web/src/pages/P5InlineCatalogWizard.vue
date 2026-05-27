<script setup lang="ts">
import { computed, ref } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailActions from '@/components/DetailActions.vue';
import { invokeActionStub, pushToast } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';
import { canAuthorInlineCatalog } from '@/lib/requestFlowRoles';

const role = getProductRole();
const canAuthor = computed(() => canAuthorInlineCatalog(role.value));

type Stage = 'draft_unsubmitted' | 'metadata_filled' | 'submitted';

// 默认值与 scripts/customer_demo_j2.py 对齐：sd-default 济南公安局 / 区划 370100。
// 业务方可现场改写覆盖到目标部门。
const defaultOwnerOrg = '11370000MB284651XL';
const defaultRegion = '370100';

const title = ref('');
const ownerOrg = ref(defaultOwnerOrg);
const regionCode = ref(defaultRegion);
const note = ref('');

const catalogCode = ref('');
const stage = ref<Stage>('draft_unsubmitted');
const lifecycleStatus = ref<string>('');
const busy = ref(false);

function _newCatalogCode(): string {
  const ts = Date.now().toString(36);
  const rnd = Math.random().toString(36).slice(2, 6);
  return `j2-inline-${ts}-${rnd}`;
}

const submitted = computed(() => stage.value === 'submitted');
const canRunStep1 = computed(() => canAuthor.value && !catalogCode.value && title.value.trim().length > 0);
const canRunStep2 = computed(() => canAuthor.value && Boolean(catalogCode.value) && stage.value === 'draft_unsubmitted');
const canRunStep3 = computed(() => canAuthor.value && Boolean(catalogCode.value) && stage.value === 'metadata_filled');

async function createDraft() {
  if (!canRunStep1.value || busy.value) return;
  busy.value = true;
  try {
    const code = _newCatalogCode();
    const result = await invokeActionStub({
      skillId: 'catalog.entry.create_draft',
      payload: {
        catalog_code: code,
        title: title.value.trim(),
        owner_org_id: ownerOrg.value.trim() || defaultOwnerOrg,
        region_code: regionCode.value.trim() || defaultRegion,
      },
      successTitle: '已创建目录草稿',
      role: 'ROLE_ORGAN_OPERATER',
      refreshSnapshotAfter: false,
    });
    if (!result.ok) return;
    catalogCode.value = code;
    stage.value = 'draft_unsubmitted';
    const root = (result.data ?? {}) as Record<string, unknown>;
    const inner = (root.result ?? root) as Record<string, unknown>;
    lifecycleStatus.value = String(inner.lifecycle_status ?? 'draft');
  } finally {
    busy.value = false;
  }
}

async function saveMetadata() {
  if (!canRunStep2.value || busy.value) return;
  busy.value = true;
  try {
    const result = await invokeActionStub({
      skillId: 'catalog.entry.update',
      payload: {
        catalog_code: catalogCode.value,
        title: title.value.trim(),
        owner_org_id: ownerOrg.value.trim() || defaultOwnerOrg,
        region_code: regionCode.value.trim() || defaultRegion,
        summary_json: { stage: 'metadata_filled', note: note.value.trim() || null },
      },
      successTitle: '已保存元数据',
      role: 'ROLE_ORGAN_OPERATER',
      refreshSnapshotAfter: false,
    });
    if (!result.ok) return;
    stage.value = 'metadata_filled';
    const root = (result.data ?? {}) as Record<string, unknown>;
    const inner = (root.result ?? root) as Record<string, unknown>;
    lifecycleStatus.value = String(inner.lifecycle_status ?? lifecycleStatus.value);
  } finally {
    busy.value = false;
  }
}

async function submitForReview() {
  if (!canRunStep3.value || busy.value) return;
  busy.value = true;
  try {
    const result = await invokeActionStub({
      skillId: 'catalog.entry.submit_review',
      payload: { catalog_code: catalogCode.value },
      successTitle: '已提交部门审核',
      role: 'ROLE_ORGAN_OPERATER',
      refreshSnapshotAfter: true,
    });
    if (!result.ok) return;
    stage.value = 'submitted';
    const root = (result.data ?? {}) as Record<string, unknown>;
    const inner = (root.result ?? root) as Record<string, unknown>;
    lifecycleStatus.value = String(inner.lifecycle_status ?? 'pending_review');
  } finally {
    busy.value = false;
  }
}

function startAnother() {
  pushToast({ kind: 'info', title: '已重置，可继续在线编制下一条目录' });
  title.value = '';
  note.value = '';
  ownerOrg.value = defaultOwnerOrg;
  regionCode.value = defaultRegion;
  catalogCode.value = '';
  lifecycleStatus.value = '';
  stage.value = 'draft_unsubmitted';
}
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/provider">← 提供方管理</a></nav>
    <section class="panel">
      <PageFocusHeader
        title="在线编制目录"
        meta="部门操作员从零新建目录 · 补元数据 · 提交部门审核（J2 第 1-4 步）"
        :links="[
          { label: '目录审核收件箱', href: '#/provider/inbox/catalog-review' },
          { label: '反向编目', href: '#/provider/wizard/reverse-catalog' },
        ]"
      />

      <p v-if="!canAuthor" class="role-hint">
        当前岗位为「{{ role }}」；在线编制需切换为「部门操作员（ROLE_ORGAN_OPERATER）」。
      </p>

      <!-- Step 1：新建目录草稿 -->
      <section class="step">
        <h3 class="step-title">第 1 步 · 新建目录草稿</h3>
        <div class="form-row">
          <label class="field-label">目录名称<span class="req">*</span></label>
          <input
            v-model="title"
            class="gov-input"
            type="text"
            placeholder="例如：医疗救助申请人信息（部门内部目录）"
            :disabled="!canAuthor || Boolean(catalogCode)"
          />
        </div>
        <div class="form-row">
          <label class="field-label">责任单位社会信用代码（owner_org_id）</label>
          <input v-model="ownerOrg" class="gov-input" type="text" :disabled="!canAuthor || Boolean(catalogCode)" />
        </div>
        <div class="form-row">
          <label class="field-label">行政区划代码（region_code）</label>
          <input v-model="regionCode" class="gov-input gov-input-narrow" type="text" :disabled="!canAuthor || Boolean(catalogCode)" />
        </div>
        <DetailActions>
          <button
            type="button"
            class="gov-btn gov-btn-primary"
            data-testid="inline-catalog-create-btn"
            :disabled="!canRunStep1 || busy"
            @click="createDraft"
          >
            创建目录草稿
          </button>
        </DetailActions>
        <p v-if="catalogCode" class="step-done">
          已生成目录编号：<code>{{ catalogCode }}</code> · 当前状态：<strong>{{ lifecycleStatus || 'draft' }}</strong>
        </p>
      </section>

      <!-- Step 2：补元数据 -->
      <section class="step" :class="{ 'step-disabled': !catalogCode }">
        <h3 class="step-title">第 2 步 · 补充元数据</h3>
        <div class="form-row">
          <label class="field-label">补充说明（可空）</label>
          <textarea
            v-model="note"
            class="gov-textarea"
            rows="3"
            placeholder="例如：本目录覆盖 2026 年度医疗救助申请的核心信息，按月更新。"
            :disabled="!canRunStep2"
          ></textarea>
        </div>
        <DetailActions>
          <button
            type="button"
            class="gov-btn gov-btn-secondary"
            data-testid="inline-catalog-update-btn"
            :disabled="!canRunStep2 || busy"
            @click="saveMetadata"
          >
            保存元数据
          </button>
        </DetailActions>
        <p v-if="stage === 'metadata_filled' || stage === 'submitted'" class="step-done">
          元数据已保存，当前状态：<strong>{{ lifecycleStatus }}</strong>
        </p>
      </section>

      <!-- Step 3：提交部门审 -->
      <section class="step" :class="{ 'step-disabled': stage === 'draft_unsubmitted' }">
        <h3 class="step-title">第 3 步 · 提交部门审核</h3>
        <p class="step-hint">提交后流转至部门管理员，依次经部门审 → 平台审 → 发布。</p>
        <DetailActions>
          <button
            type="button"
            class="gov-btn gov-btn-primary"
            data-testid="inline-catalog-submit-btn"
            :disabled="!canRunStep3 || busy"
            @click="submitForReview"
          >
            提交部门审核
          </button>
        </DetailActions>
        <p v-if="submitted" class="step-done">
          已提交，当前状态：<strong>{{ lifecycleStatus }}</strong>。
          请通知部门管理员到
          <a href="#/provider/inbox/catalog-review">目录审核收件箱</a>
          办理；或继续
          <button type="button" class="link-btn" @click="startAnother">在线编制下一条</button>。
        </p>
      </section>
    </section>
  </main>
</template>

<style scoped>
.step { margin-top: 18px; padding: 14px 16px; border: 1px solid var(--b-border, #d4e2f4); border-radius: 8px; background: #fff; }
.step-disabled { opacity: 0.55; }
.step-title { margin: 0 0 8px; font-size: 15px; font-weight: 600; color: var(--b-text, #1f2733); }
.step-hint { margin: 0 0 8px; font-size: 13px; color: var(--b-muted, #5c6370); }
.step-done { margin: 10px 0 0; font-size: 13px; color: #2c7a2c; }
.form-row { margin-bottom: 10px; }
.field-label { display: block; font-size: 13px; color: var(--b-muted, #5c6370); margin-bottom: 4px; }
.req { color: #c0392b; margin-left: 2px; }
.gov-input { width: 100%; max-width: 480px; padding: 8px 10px; border: 1px solid var(--b-border, #d4e2f4); border-radius: 6px; font-size: 14px; }
.gov-input-narrow { max-width: 160px; }
.gov-textarea { width: 100%; max-width: 600px; padding: 8px 10px; border: 1px solid var(--b-border, #d4e2f4); border-radius: 6px; font-size: 13px; resize: vertical; font-family: inherit; }
.gov-btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid transparent; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-primary[disabled] { background: #9bbfe6; cursor: not-allowed; }
.gov-btn-secondary { background: #fff; border-color: var(--b-border, #d4e2f4); color: var(--b-text, #1f2733); }
.gov-btn-secondary[disabled] { color: #9aa5b1; cursor: not-allowed; }
.role-hint { font-size: 13px; color: var(--b-muted, #5c6370); margin: 0 0 12px; line-height: 1.5; }
.link-btn { background: none; border: 0; color: var(--b-primary, #006be6); cursor: pointer; padding: 0; font-size: inherit; text-decoration: underline; }
</style>
