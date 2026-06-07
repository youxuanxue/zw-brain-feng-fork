<script setup lang="ts">
import { computed, ref } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailActions from '@/components/DetailActions.vue';
import { invokeActionStub, pushToast } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';
import { canAuthorInlineCatalog } from '@/lib/requestFlowRoles';
import {
  SHARE_TYPE_OPTIONS,
  SHARE_WAY_OPTIONS,
  OPEN_TYPE_OPTIONS,
  UPDATE_CYCLE_OPTIONS,
  RESOURCE_FORMAT_OPTIONS,
  ITEM_TYPE_OPTIONS,
  DATA_LEVEL_OPTIONS,
  blankCatalogItem,
  catalogItemToPayload,
  type CatalogItemDraft,
} from '@/lib/catalogCompileFields';

const role = getProductRole();
const canAuthor = computed(() => canAuthorInlineCatalog(role.value));

type Stage = 'draft_unsubmitted' | 'metadata_filled' | 'submitted';

// 默认归属与脚本 scripts/customer_demo_j2.py 对齐：sd-default 济南公安局 / 区划 370100。
// 归属/区划是机器侧绑定值（owner_org_id / region_code），R12：不作为表单可见字段暴露，
// 由系统按登录岗位部门注入（此处沿用 demo 默认，业务方现场以真实部门覆盖）。
const defaultOwnerOrg = '11370000MB284651XL';
const defaultRegion = '370100';

// —— 第 1 步：基本信息（编制规范全集，summary_json 键与 catalog_service.catalog_meta() 同字典）——
const title = ref('');
const catalogType = ref(''); // 数据资源分类（summary.catalog_type）
const sourceSystem = ref(''); // 来源系统（summary.source_system）
const internalDept = ref(''); // 内部部门（summary.internal_org_name）
const domain = ref(''); // 所属领域（summary.domain）
const applicationScenario = ref(''); // 应用场景（summary.application_scenario）
const resourceFormat = ref('0200'); // 信息资源格式（summary.resource_format）
const businessUpdateCycle = ref('2'); // 业务更新周期（summary.business_update_cycle）
const dataUpdateCycle = ref('2'); // 数据更新周期（summary.data_update_cycle）
const shareWay = ref('api'); // 共享方式（summary.shared_way）
const shareType = ref('2'); // 共享类型（summary.shared_type）
const shareCondition = ref(''); // 共享条件（summary.shared_condition）
const openType = ref('3'); // 开放类型（summary.open_type）
const openCondition = ref(''); // 开放条件（summary.open_condition）
const description = ref(''); // 数据资源摘要（summary.description）

// —— 第 2 步：信息项维护（写 payload.items[]）——
const items = ref<CatalogItemDraft[]>([blankCatalogItem()]);

// —— 第 3 步：其他信息（summary_json）——
const isHandlingResult = ref('false'); // 是否办理结果数据（summary.is_handling_result）
const isEcert = ref('false'); // 是否电子证照（summary.is_ecert）
const contactName = ref(''); // 联系人（summary.contact_name）
const contactPhone = ref(''); // 联系电话（summary.contact_phone）
const contactEmail = ref(''); // 联系人邮箱（summary.contact_email）
const officePhone = ref(''); // 办公电话（summary.office_phone）

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

// 基本信息 summary_json：键名与详情端 catalog_meta() / accessPolicy() 读取的键一一对应。
function baseSummary(): Record<string, unknown> {
  return {
    catalog_type: catalogType.value.trim() || null,
    source_system: sourceSystem.value.trim() || null,
    internal_org_name: internalDept.value.trim() || null,
    domain: domain.value.trim() || null,
    application_scenario: applicationScenario.value.trim() || null,
    resource_format: resourceFormat.value || null,
    business_update_cycle: businessUpdateCycle.value || null,
    data_update_cycle: dataUpdateCycle.value || null,
    // updateCycle 单值（详情首屏决策行）取业务更新周期，与编制规范折叠块的双周期一致。
    update_cycle: businessUpdateCycle.value || null,
    shared_way: shareWay.value || null,
    shared_type: shareType.value || null,
    shared_condition: shareCondition.value.trim() || null,
    open_type: openType.value || null,
    open_condition: openCondition.value.trim() || null,
    description: description.value.trim() || null,
  };
}

function otherSummary(): Record<string, unknown> {
  return {
    is_handling_result: isHandlingResult.value === 'true',
    is_ecert: isEcert.value === 'true',
    contact_name: contactName.value.trim() || null,
    contact_phone: contactPhone.value.trim() || null,
    contact_email: contactEmail.value.trim() || null,
    office_phone: officePhone.value.trim() || null,
  };
}

function itemPayloads(): Record<string, unknown>[] {
  return items.value
    .filter((it) => it.title.trim())
    .map((it, idx) => catalogItemToPayload(it, catalogCode.value, idx));
}

function addItem() {
  items.value.push(blankCatalogItem());
}
function removeItem(i: number) {
  if (items.value.length > 1) items.value.splice(i, 1);
}
function moveItem(i: number, dir: -1 | 1) {
  const j = i + dir;
  if (j < 0 || j >= items.value.length) return;
  const tmp = items.value[i];
  items.value[i] = items.value[j];
  items.value[j] = tmp;
}

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
        owner_org_id: defaultOwnerOrg,
        region_code: defaultRegion,
        summary_json: baseSummary(),
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
        owner_org_id: defaultOwnerOrg,
        region_code: defaultRegion,
        summary_json: { ...baseSummary(), ...otherSummary(), stage: 'metadata_filled' },
        items: itemPayloads(),
      },
      successTitle: '已保存元数据与信息项',
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
  catalogType.value = '';
  sourceSystem.value = '';
  internalDept.value = '';
  domain.value = '';
  applicationScenario.value = '';
  resourceFormat.value = '0200';
  businessUpdateCycle.value = '2';
  dataUpdateCycle.value = '2';
  shareWay.value = 'api';
  shareType.value = '2';
  shareCondition.value = '';
  openType.value = '3';
  openCondition.value = '';
  description.value = '';
  items.value = [blankCatalogItem()];
  isHandlingResult.value = 'false';
  isEcert.value = 'false';
  contactName.value = '';
  contactPhone.value = '';
  contactEmail.value = '';
  officePhone.value = '';
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
        meta="基本信息维护 · 信息项维护 · 其他信息（对标旧平台目录管理在线编制三步）"
        :links="[
          { label: '目录审核收件箱', href: '#/provider/inbox/catalog-review' },
          { label: '反向编目', href: '#/provider/wizard/reverse-catalog' },
        ]"
      />

      <p v-if="!canAuthor" class="role-hint">
        在线编制是部门操作员的职责。当前岗位为「{{ role }}」，暂无编制权限；请切换为「部门操作员」后再来此新建目录。
      </p>

      <!-- Step 1：基本信息维护 -->
      <section class="step">
        <h3 class="step-title">第 1 步 · 基本信息维护</h3>
        <div class="grid2">
          <div class="form-row span2">
            <label class="field-label">数据资源目录名称<span class="req">*</span></label>
            <input
              v-model="title"
              class="gov-input"
              type="text"
              placeholder="例如：医疗救助申请人信息"
              :disabled="!canAuthor || Boolean(catalogCode)"
            />
          </div>
          <div class="form-row">
            <label class="field-label">数据资源分类</label>
            <input v-model="catalogType" class="gov-input" type="text" placeholder="例如：民政服务" :disabled="!canAuthor || Boolean(catalogCode)" />
          </div>
          <div class="form-row">
            <label class="field-label">来源系统</label>
            <input v-model="sourceSystem" class="gov-input" type="text" placeholder="例如：医疗救助建模系统" :disabled="!canAuthor || Boolean(catalogCode)" />
          </div>
          <div class="form-row">
            <label class="field-label">内部部门</label>
            <input v-model="internalDept" class="gov-input" type="text" placeholder="例如：社会救助科" :disabled="!canAuthor || Boolean(catalogCode)" />
          </div>
          <div class="form-row">
            <label class="field-label">所属领域</label>
            <input v-model="domain" class="gov-input" type="text" placeholder="例如：社会保障" :disabled="!canAuthor || Boolean(catalogCode)" />
          </div>
          <div class="form-row span2">
            <label class="field-label">应用场景</label>
            <input v-model="applicationScenario" class="gov-input" type="text" placeholder="例如：用于医疗救助资格审核与待遇核算" :disabled="!canAuthor || Boolean(catalogCode)" />
          </div>
          <div class="form-row">
            <label class="field-label">信息资源格式</label>
            <select v-model="resourceFormat" class="gov-input" :disabled="!canAuthor || Boolean(catalogCode)">
              <option v-for="o in RESOURCE_FORMAT_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
          </div>
          <div class="form-row">
            <label class="field-label">共享方式</label>
            <select v-model="shareWay" class="gov-input" :disabled="!canAuthor || Boolean(catalogCode)">
              <option v-for="o in SHARE_WAY_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
          </div>
          <div class="form-row">
            <label class="field-label">业务更新周期</label>
            <select v-model="businessUpdateCycle" class="gov-input" :disabled="!canAuthor || Boolean(catalogCode)">
              <option v-for="o in UPDATE_CYCLE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
          </div>
          <div class="form-row">
            <label class="field-label">数据更新周期</label>
            <select v-model="dataUpdateCycle" class="gov-input" :disabled="!canAuthor || Boolean(catalogCode)">
              <option v-for="o in UPDATE_CYCLE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
          </div>
          <div class="form-row">
            <label class="field-label">共享类型</label>
            <select v-model="shareType" class="gov-input" :disabled="!canAuthor || Boolean(catalogCode)">
              <option v-for="o in SHARE_TYPE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
          </div>
          <div class="form-row">
            <label class="field-label">开放类型</label>
            <select v-model="openType" class="gov-input" :disabled="!canAuthor || Boolean(catalogCode)">
              <option v-for="o in OPEN_TYPE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
          </div>
          <div class="form-row span2">
            <label class="field-label">共享条件</label>
            <input v-model="shareCondition" class="gov-input" type="text" placeholder="例如：根据个人信息保护要求，按授权范围共享" :disabled="!canAuthor || Boolean(catalogCode)" />
          </div>
          <div class="form-row span2">
            <label class="field-label">开放条件</label>
            <input v-model="openCondition" class="gov-input" type="text" placeholder="例如：不可对社会开放" :disabled="!canAuthor || Boolean(catalogCode)" />
          </div>
          <div class="form-row span2">
            <label class="field-label">数据资源摘要</label>
            <textarea v-model="description" class="gov-textarea" rows="3" placeholder="一句话说明本目录覆盖的数据范围与用途。" :disabled="!canAuthor || Boolean(catalogCode)"></textarea>
          </div>
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
          已生成目录草稿 · 当前状态：<strong>{{ lifecycleStatus || 'draft' }}</strong>
        </p>
      </section>

      <!-- Step 2：信息项维护 -->
      <section class="step" :class="{ 'step-disabled': !catalogCode }">
        <h3 class="step-title">第 2 步 · 信息项维护</h3>
        <p class="step-hint">逐条登记目录下的字段级信息项（对标旧平台「信息项维护」）。信息项名称必填，其余可空。</p>
        <div v-for="(it, i) in items" :key="i" class="item-card">
          <div class="item-grid">
            <div>
              <label class="field-label">信息项名称<span class="req">*</span></label>
              <input v-model="it.title" class="gov-input" placeholder="例如：姓名" :disabled="!canRunStep2" />
            </div>
            <div>
              <label class="field-label">英文名称</label>
              <input v-model="it.englishName" class="gov-input" placeholder="例如：xm" :disabled="!canRunStep2" />
            </div>
            <div>
              <label class="field-label">信息项类型</label>
              <select v-model="it.itemType" class="gov-input" :disabled="!canRunStep2">
                <option v-for="o in ITEM_TYPE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
              </select>
            </div>
            <div>
              <label class="field-label">信息项长度</label>
              <input v-model="it.itemLength" class="gov-input" placeholder="例如：50" :disabled="!canRunStep2" />
            </div>
            <div>
              <label class="field-label">共享类型</label>
              <select v-model="it.shareType" class="gov-input" :disabled="!canRunStep2">
                <option v-for="o in SHARE_TYPE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
              </select>
            </div>
            <div>
              <label class="field-label">数据级别</label>
              <select v-model="it.dataLevel" class="gov-input" :disabled="!canRunStep2">
                <option v-for="o in DATA_LEVEL_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
              </select>
            </div>
            <div class="item-span2">
              <label class="field-label">共享条件</label>
              <input v-model="it.shareCondition" class="gov-input" placeholder="例如：需符合数据应用场景" :disabled="!canRunStep2" />
            </div>
            <div class="item-span2">
              <label class="field-label">备注</label>
              <input v-model="it.note" class="gov-input" placeholder="可空" :disabled="!canRunStep2" />
            </div>
          </div>
          <div class="item-ops">
            <button type="button" class="link-btn" :disabled="!canRunStep2 || i === 0" @click="moveItem(i, -1)">上移</button>
            <button type="button" class="link-btn" :disabled="!canRunStep2 || i === items.length - 1" @click="moveItem(i, 1)">下移</button>
            <button type="button" class="link-btn danger" :disabled="!canRunStep2 || items.length <= 1" @click="removeItem(i)">删除</button>
          </div>
        </div>
        <button type="button" class="gov-btn gov-btn-secondary add-item" :disabled="!canRunStep2" @click="addItem">+ 增加信息项</button>
      </section>

      <!-- Step 3：其他信息 + 保存元数据 + 提交 -->
      <section class="step" :class="{ 'step-disabled': !catalogCode }">
        <h3 class="step-title">第 3 步 · 其他信息</h3>
        <div class="grid2">
          <div class="form-row">
            <label class="field-label">是否为政务事项办理结果数据</label>
            <select v-model="isHandlingResult" class="gov-input" :disabled="!canRunStep2">
              <option value="false">否</option>
              <option value="true">是</option>
            </select>
          </div>
          <div class="form-row">
            <label class="field-label">是否电子证照</label>
            <select v-model="isEcert" class="gov-input" :disabled="!canRunStep2">
              <option value="false">否</option>
              <option value="true">是</option>
            </select>
          </div>
          <div class="form-row">
            <label class="field-label">联系人</label>
            <input v-model="contactName" class="gov-input" placeholder="例如：王丽莎" :disabled="!canRunStep2" />
          </div>
          <div class="form-row">
            <label class="field-label">联系电话</label>
            <input v-model="contactPhone" class="gov-input" placeholder="例如：17890786758" :disabled="!canRunStep2" />
          </div>
          <div class="form-row">
            <label class="field-label">联系人邮箱</label>
            <input v-model="contactEmail" class="gov-input" placeholder="例如：123@example.gov.cn" :disabled="!canRunStep2" />
          </div>
          <div class="form-row">
            <label class="field-label">办公电话</label>
            <input v-model="officePhone" class="gov-input" placeholder="例如：010-87658977" :disabled="!canRunStep2" />
          </div>
        </div>
        <DetailActions>
          <button
            type="button"
            class="gov-btn gov-btn-secondary"
            data-testid="inline-catalog-update-btn"
            :disabled="!canRunStep2 || busy"
            @click="saveMetadata"
          >
            保存元数据与信息项
          </button>
        </DetailActions>
        <p v-if="stage === 'metadata_filled' || stage === 'submitted'" class="step-done">
          元数据与信息项已保存，当前状态：<strong>{{ lifecycleStatus }}</strong>
        </p>
      </section>

      <!-- Step 4：提交部门审核 -->
      <section class="step" :class="{ 'step-disabled': stage === 'draft_unsubmitted' }">
        <h3 class="step-title">第 4 步 · 提交部门审核</h3>
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
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px 16px; }
.form-row { margin-bottom: 4px; }
.form-row.span2 { grid-column: 1 / -1; }
.field-label { display: block; font-size: 13px; color: var(--b-muted, #5c6370); margin-bottom: 4px; }
.req { color: #c0392b; margin-left: 2px; }
.gov-input { width: 100%; padding: 8px 10px; border: 1px solid var(--b-border, #d4e2f4); border-radius: 6px; font-size: 14px; box-sizing: border-box; }
.gov-textarea { width: 100%; padding: 8px 10px; border: 1px solid var(--b-border, #d4e2f4); border-radius: 6px; font-size: 13px; resize: vertical; font-family: inherit; box-sizing: border-box; }
.gov-btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid transparent; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-primary[disabled] { background: #9bbfe6; cursor: not-allowed; }
.gov-btn-secondary { background: #fff; border-color: var(--b-border, #d4e2f4); color: var(--b-text, #1f2733); }
.gov-btn-secondary[disabled] { color: #9aa5b1; cursor: not-allowed; }
.role-hint { font-size: 13px; color: var(--b-muted, #5c6370); margin: 0 0 12px; line-height: 1.5; }
.link-btn { background: none; border: 0; color: var(--b-primary, #006be6); cursor: pointer; padding: 0; font-size: 13px; text-decoration: underline; }
.link-btn:disabled { color: #9aa5b1; cursor: not-allowed; text-decoration: none; }
.link-btn.danger { color: #c0392b; }
.item-card { border: 1px solid var(--b-border, #d4e2f4); border-radius: 8px; padding: 12px; margin-bottom: 10px; background: #fafcff; }
.item-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px 12px; }
.item-span2 { grid-column: span 2; }
.item-ops { margin-top: 8px; display: flex; gap: 14px; }
.add-item { margin-top: 4px; }
</style>
