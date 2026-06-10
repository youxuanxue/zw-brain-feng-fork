<script setup lang="ts">
import { computed, ref } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailActions from '@/components/DetailActions.vue';
import { useProvider, useSnapshot } from '@/composables/useSnapshot';
import { invokeActionStub, pushToast } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';
import { canPerformAction } from '@/lib/pageAccess';
import {
  SHARE_TYPE_OPTIONS,
  OPEN_TYPE_OPTIONS,
  DATA_GRADE_OPTIONS,
  AUTH_MODE_OPTIONS,
} from '@/lib/catalogCompileFields';

// 代理服务注册向导（0605 反馈 6.5#6） —— 用户自助输入「原始接口地址」，代理到平台共享、关联数据目录。
// 对标旧「融合服务管理系统 → 创建代理服务」四步。接 resource.api.register（channel_binding=
// 代理地址）。已注册服务列表读真实 resource_asset(kind=api)，不再读 seed 演示服务。

const provider = useProvider();
const { source } = useSnapshot();
const role = getProductRole();

// 角色门（0605 验收回合角色口径，业务方 2026-06-08 sign-off）：注册/编辑/提交审核 = 部门操作员 + 部门管理员；
// 审核发布/下线 = 部门管理员。无权岗位（业务运营员）整段注册表单 + 行内操作均不渲染（守「无权 = 不可见」）。
const canRegisterApi = computed(() => canPerformAction('resource.api.register', role.value));
const canSubmitReviewApi = computed(() => canPerformAction('resource.api.submit_review', role.value));
// G4：服务注册审核（pending_review → 待发布）按 resource.api.review 动作键判，与后端
// policy.resource.api.review={ROLE_ORGAN_MANAGER} set-equal。补此行内动作，让「待审核服务」深链可办理。
const canReviewApi = computed(() => canPerformAction('resource.api.review', role.value));
const canPublishApi = computed(() => canPerformAction('resource.api.publish', role.value));
// 下线（withdraw→retired）按自身动作键判，与后端 policy.resource.api.withdraw set-equal（归部门管理员）。
const canWithdrawApi = computed(() => canPerformAction('resource.api.withdraw', role.value));
// 列表是否需要「操作」列：任一生命周期动作对当前岗位可见才出列（无权岗位列表保持只读）。
const showServiceActions = computed(
  () => canSubmitReviewApi.value || canReviewApi.value || canPublishApi.value || canWithdrawApi.value,
);

// —— 已注册 API 服务列表（真实数据，注册产出即时可见）——
const services = computed(() => {
  const list = (provider.value.services as unknown[] | undefined) ?? [];
  return list.map((s) => {
    const it = s as Record<string, unknown>;
    return {
      id: String(it.id ?? ''),
      name: String(it.name ?? ''),
      status: String(it.status ?? ''),
      // 原始生命周期码（draft/pending_review/approved_pending_publish/active…）驱动行内操作分流；
      // status 是白话标签仅供展示，不参与判定。
      lifecycleStatus: String(it.lifecycle_status ?? ''),
      catalogCode: String(it.catalog_code ?? ''),
      note: String(it.note ?? ''),
    };
  });
});

// 可关联的数据目录（来自 provider 目录列表）。
const catalogOptions = computed(() => {
  const list = (provider.value.catalogs as unknown[] | undefined) ?? [];
  return list
    .map((c) => c as Record<string, unknown>)
    .map((c) => ({ id: String(c.id ?? c.catalog_code ?? ''), title: String(c.title ?? c.name ?? c.id ?? '') }))
    .filter((c) => c.id);
});

const headerMeta = computed(() => {
  if (source.value !== 'live') return '正在加载……';
  const n = services.value.length;
  if (!canRegisterApi.value) {
    // 非注册岗位（业务运营员）：只读查看，不提示「注册」（注册岗位口径，2026-06-08 sign-off）。
    return n ? `已注册 ${n} 个 API 服务` : '尚无已注册 API 服务';
  }
  // T8：表单默认收起，提示点页头主按钮开始。
  return n ? `已注册 ${n} 个 API 服务 · 可继续注册新代理服务` : '尚无已注册 API 服务 · 点「注册代理服务」开始';
});

// —— 注册表单（四步基本信息/网络/配置/技术支持，同屏展开，无分步切换）——
// ① 服务基本信息
const serviceName = ref('');
const relatedCatalog = ref('');
const ownerDept = ref('省大数据局'); // 灰色只读（按登录岗位部门，demo 默认）
const sourceSystem = ref('');
const shareType = ref('2');
const openType = ref('3');
const authMode = ref('provider');
const dataGrade = ref('general');
const description = ref('');

// ② 网络信息（原始接口地址 → channel_binding）
const originalUrl = ref('');
const apiType = ref('rest');
const httpMethod = ref('GET');
const route = ref('');

// ③ 配置（→ gateway_policy_json）
const timeoutMs = ref('5000');
const cacheTtl = ref('0');
const paramNote = ref('');

// ④ 技术支持（→ summary_json）
const techContact = ref('');
const techPhone = ref('');

const busy = ref(false);
const newResourceCode = ref('');

// T8（6.5#6）：四步表单默认收起，点页头主按钮才展开——避免常驻列表下方喧宾夺主。
// 用 v-show 保留已填内容（折叠不清空）。
const showRegisterForm = ref(false);

function _newResourceCode(): string {
  const ts = Date.now().toString(36);
  const rnd = Math.random().toString(36).slice(2, 6);
  return `j2-api-proxy-${ts}-${rnd}`;
}

const canRegister = computed(
  () => serviceName.value.trim().length >= 3 && originalUrl.value.trim().length > 0 && description.value.trim().length >= 30,
);

function buildPayload(): Record<string, unknown> {
  const code = _newResourceCode();
  return {
    resource_code: code,
    resource_kind: 'api',
    title: serviceName.value.trim(),
    catalog_code: relatedCatalog.value || undefined,
    // 数据分级/共享/授权落 access_policy_json（无需新表）。
    access_policy_json: {
      shared_type: shareType.value,
      open_type: openType.value,
      auth_mode: authMode.value,
      data_grade: dataGrade.value,
    },
    // 配置（超时/缓存/参数）→ qos_policy_json（资产级网关策略）。
    qos_policy_json: {
      timeout_ms: Number(timeoutMs.value) || null,
      cache_ttl_seconds: Number(cacheTtl.value) || 0,
      param_note: paramNote.value.trim() || null,
    },
    // 技术支持 + 来源系统 → summary_json。
    summary_json: {
      title: serviceName.value.trim(),
      description: description.value.trim(),
      source_system: sourceSystem.value.trim() || null,
      internal_org_name: ownerDept.value,
      tech_contact: techContact.value.trim() || null,
      tech_phone: techPhone.value.trim() || null,
    },
    // 原始接口地址 → 代理 channel_binding（endpoint_ref.proxy_url / route_ref=代理路由）。
    channel_binding: {
      binding_code: `${code}#proxy`,
      channel_kind: 'api_gateway',
      route_ref: route.value.trim() || originalUrl.value.trim(),
      endpoint_ref: {
        proxy_url: originalUrl.value.trim(),
        api_type: apiType.value,
        http_method: httpMethod.value,
      },
      gateway_policy_json: {
        timeout_ms: Number(timeoutMs.value) || null,
        cache_ttl_seconds: Number(cacheTtl.value) || 0,
      },
      lifecycle_status: 'draft',
    },
    confirmed: true,
  };
}

async function register() {
  if (!canRegister.value || busy.value) return;
  busy.value = true;
  try {
    const payload = buildPayload();
    const res = await invokeActionStub({
      skillId: 'resource.api.register',
      payload,
      successTitle: '代理服务已注册（草稿）',
      role: role.value,
      refreshSnapshotAfter: true,
    });
    if (!res.ok) return;
    newResourceCode.value = String(payload.resource_code ?? '');
  } finally {
    busy.value = false;
  }
}

async function submitReview() {
  if (!newResourceCode.value || busy.value) return;
  busy.value = true;
  try {
    await invokeActionStub({
      skillId: 'resource.api.submit_review',
      payload: { resource_code: newResourceCode.value },
      successTitle: '已提交服务化审核',
      role: role.value,
      refreshSnapshotAfter: true,
    });
  } finally {
    busy.value = false;
  }
}

// —— 已注册服务行内生命周期操作（T7，0605 反馈 6.5#6）——
// 既有能力接线，仅需 resource_code：草稿→提交审核、待发布→发布、已发布→下线。
// 可见性由 lifecycle_status × 角色门双重决定（无权/不在该态即不渲染）。
const rowBusy = ref('');

async function submitReviewRow(code: string) {
  if (!code || rowBusy.value) return;
  rowBusy.value = code;
  try {
    await invokeActionStub({
      skillId: 'resource.api.submit_review',
      payload: { resource_code: code },
      successTitle: '已提交服务化审核',
      role: role.value,
      refreshSnapshotAfter: true,
    });
  } finally {
    rowBusy.value = '';
  }
}

async function reviewRow(code: string) {
  // G4：服务注册审核通过（pending_review → approved_pending_publish），与挂接资产审核同后端转换。
  if (!code || rowBusy.value) return;
  rowBusy.value = code;
  try {
    await invokeActionStub({
      skillId: 'resource.api.review',
      payload: { resource_code: code, decision: 'approve' },
      successTitle: '服务注册已审核通过，待发布',
      role: role.value,
      refreshSnapshotAfter: true,
    });
  } finally {
    rowBusy.value = '';
  }
}

async function publishRow(code: string) {
  if (!code || rowBusy.value) return;
  rowBusy.value = code;
  try {
    await invokeActionStub({
      skillId: 'resource.api.publish',
      payload: { resource_code: code },
      successTitle: '代理服务已发布',
      role: role.value,
      refreshSnapshotAfter: true,
    });
  } finally {
    rowBusy.value = '';
  }
}

async function withdrawRow(code: string, name: string) {
  if (!code || rowBusy.value) return;
  // 下线是把已发布服务退役，需用户二次确认（不可一键误触）。
  if (!window.confirm(`确认下线代理服务「${name || code}」？下线后调用方将无法访问。`)) return;
  rowBusy.value = code;
  try {
    await invokeActionStub({
      skillId: 'resource.api.withdraw',
      payload: { resource_code: code },
      successTitle: '代理服务已下线',
      role: role.value,
      refreshSnapshotAfter: true,
    });
  } finally {
    rowBusy.value = '';
  }
}

function resetForm() {
  pushToast({ kind: 'info', title: '已重置，可继续注册下一个代理服务' });
  serviceName.value = '';
  relatedCatalog.value = '';
  sourceSystem.value = '';
  shareType.value = '2';
  openType.value = '3';
  authMode.value = 'provider';
  dataGrade.value = 'general';
  description.value = '';
  originalUrl.value = '';
  apiType.value = 'rest';
  httpMethod.value = 'GET';
  route.value = '';
  timeoutMs.value = '5000';
  cacheTtl.value = '0';
  paramNote.value = '';
  techContact.value = '';
  techPhone.value = '';
  newResourceCode.value = '';
}
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/provider">← 提供方管理</a></nav>
    <section class="panel">
      <PageFocusHeader
        title="代理服务注册向导"
        :meta="headerMeta"
        :links="[{ label: '质量规则向导', href: '#/provider/wizard/quality-rule' }]"
      />

      <!-- 已注册 API 服务列表（真实数据） -->
      <section v-if="source === 'live' && services.length" class="reg-list">
        <h3 class="block-title">已注册的 API 服务</h3>
        <table class="focus-table">
          <thead>
            <tr>
              <th>服务名称</th><th>状态</th><th>关联数据目录</th><th>说明</th>
              <th v-if="showServiceActions">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in services" :key="s.id">
              <td>{{ s.name }}</td>
              <td>{{ s.status }}</td>
              <td>{{ s.catalogCode || '未关联' }}</td>
              <td>{{ s.note || '未提供' }}</td>
              <td v-if="showServiceActions" class="row-actions">
                <!-- 草稿：提交审核（操作员/管理员）。 -->
                <button
                  v-if="s.lifecycleStatus === 'draft' && canSubmitReviewApi"
                  type="button" class="gov-btn gov-btn-link" :disabled="Boolean(rowBusy)"
                  @click="submitReviewRow(s.id)"
                >提交审核</button>
                <!-- 待审核：审核通过（部门管理员）。G4：补齐 pending_review 的审核动作。 -->
                <button
                  v-if="s.lifecycleStatus === 'pending_review' && canReviewApi"
                  type="button" class="gov-btn gov-btn-link" :disabled="Boolean(rowBusy)"
                  @click="reviewRow(s.id)"
                >审核通过</button>
                <!-- 待发布：发布（部门管理员）。 -->
                <button
                  v-if="s.lifecycleStatus === 'approved_pending_publish' && canPublishApi"
                  type="button" class="gov-btn gov-btn-link" :disabled="Boolean(rowBusy)"
                  @click="publishRow(s.id)"
                >发布</button>
                <!-- 已发布：下线（部门管理员）。 -->
                <button
                  v-if="s.lifecycleStatus === 'active' && canWithdrawApi"
                  type="button" class="gov-btn gov-btn-link gov-btn-danger" :disabled="Boolean(rowBusy)"
                  @click="withdrawRow(s.id, s.name)"
                >下线</button>
                <!-- 当前态对本岗位无可执行动作时，诚实显短横（不伪造按钮）。 -->
                <span
                  v-if="!((s.lifecycleStatus === 'draft' && canSubmitReviewApi) || (s.lifecycleStatus === 'pending_review' && canReviewApi) || (s.lifecycleStatus === 'approved_pending_publish' && canPublishApi) || (s.lifecycleStatus === 'active' && canWithdrawApi))"
                  class="row-actions-none"
                >—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <!-- T8+T6：注册入口（默认收起，点击展开）—— 仅注册岗位（部门操作员/管理员）可见（业务方 2026-06-08 sign-off，无权 = 不可见）。 -->
      <div v-if="canRegisterApi" class="reg-actions">
        <button
          type="button"
          class="gov-btn gov-btn-primary"
          data-testid="api-register-toggle"
          @click="showRegisterForm = !showRegisterForm"
        >
          {{ showRegisterForm ? '收起注册表单' : '＋ 注册代理服务' }}
        </button>
      </div>

      <!-- 代理服务注册（四步表单）—— 注册岗位可见(v-if) + 默认收起(v-show)。 -->
      <section v-if="canRegisterApi" v-show="showRegisterForm" class="reg-form" data-testid="api-register-form">

        <h3 class="block-title">注册新代理服务</h3>

        <!-- ① 服务基本信息 -->
        <div class="step-block">
          <h4 class="step-h">① 服务基本信息</h4>
          <div class="grid2">
            <div class="span2"><label class="field-label">服务名称（3-200 字符）<span class="req">*</span></label><input v-model="serviceName" class="gov-input" placeholder="例如：养老保险信息查询服务" /></div>
            <div>
              <label class="field-label">关联数据目录</label>
              <select v-model="relatedCatalog" class="gov-input">
                <option value="">不关联</option>
                <option v-for="c in catalogOptions" :key="c.id" :value="c.id">{{ c.title }}</option>
              </select>
            </div>
            <div><label class="field-label">所属部门</label><input :value="ownerDept" class="gov-input" disabled /></div>
            <div><label class="field-label">来源系统</label><input v-model="sourceSystem" class="gov-input" placeholder="例如：养老保险建模系统" /></div>
            <div>
              <label class="field-label">数据分级（一般 / 重要 / 核心）</label>
              <select v-model="dataGrade" class="gov-input">
                <option v-for="o in DATA_GRADE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
              </select>
            </div>
            <div>
              <label class="field-label">共享类型</label>
              <select v-model="shareType" class="gov-input">
                <option v-for="o in SHARE_TYPE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
              </select>
            </div>
            <div>
              <label class="field-label">开放类型</label>
              <select v-model="openType" class="gov-input">
                <option v-for="o in OPEN_TYPE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
              </select>
            </div>
            <div>
              <label class="field-label">授权方式</label>
              <select v-model="authMode" class="gov-input">
                <option v-for="o in AUTH_MODE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
              </select>
            </div>
            <div class="span2"><label class="field-label">描述（≥30 字，须体现服务价值）<span class="req">*</span></label><textarea v-model="description" class="gov-textarea" rows="2" placeholder="说明该服务提供什么数据、面向哪些业务场景。"></textarea></div>
          </div>
        </div>

        <!-- ② 网络信息 -->
        <div class="step-block">
          <h4 class="step-h">② 网络信息</h4>
          <div class="grid2">
            <div class="span2"><label class="field-label">原始接口地址<span class="req">*</span></label><input v-model="originalUrl" class="gov-input" placeholder="例如：https://10.110.16.133/api/pension/query" /></div>
            <div>
              <label class="field-label">接口类型</label>
              <select v-model="apiType" class="gov-input">
                <option value="rest">REST</option>
                <option value="soap">SOAP</option>
              </select>
            </div>
            <div>
              <label class="field-label">请求方法</label>
              <select v-model="httpMethod" class="gov-input">
                <option value="GET">GET</option>
                <option value="POST">POST</option>
              </select>
            </div>
            <div class="span2"><label class="field-label">代理路由（可空，默认取原始地址）</label><input v-model="route" class="gov-input" placeholder="例如：/share/pension/query" /></div>
          </div>
        </div>

        <!-- ③ 配置 -->
        <div class="step-block">
          <h4 class="step-h">③ 配置</h4>
          <div class="grid2">
            <div><label class="field-label">超时（毫秒）</label><input v-model="timeoutMs" class="gov-input" placeholder="5000" /></div>
            <div><label class="field-label">缓存时长（秒，0=不缓存）</label><input v-model="cacheTtl" class="gov-input" placeholder="0" /></div>
            <div class="span2"><label class="field-label">参数说明</label><input v-model="paramNote" class="gov-input" placeholder="例如：必传 id_card；可选 page/size" /></div>
          </div>
        </div>

        <!-- ④ 技术支持 -->
        <div class="step-block">
          <h4 class="step-h">④ 技术支持</h4>
          <div class="grid2">
            <div><label class="field-label">技术联系人</label><input v-model="techContact" class="gov-input" placeholder="例如：王四" /></div>
            <div><label class="field-label">联系电话</label><input v-model="techPhone" class="gov-input" placeholder="例如：17890786758" /></div>
          </div>
        </div>

        <DetailActions>
          <button type="button" class="gov-btn gov-btn-primary" :disabled="!canRegister || busy || Boolean(newResourceCode)" @click="register">注册代理服务（草稿）</button>
          <button type="button" class="gov-btn gov-btn-secondary" :disabled="!newResourceCode || busy" @click="submitReview">提交服务化审核</button>
          <button v-if="newResourceCode" type="button" class="gov-btn gov-btn-secondary" @click="resetForm">注册下一个</button>
        </DetailActions>
        <p v-if="newResourceCode" class="step-done">代理服务已注册为草稿，可提交服务化审核或继续注册下一个。</p>
        <p v-if="!canRegister" class="form-hint">服务名称（≥3 字）、原始接口地址、描述（≥30 字）为必填。</p>
      </section>
    </section>
  </main>
</template>

<style scoped>
.reg-actions { margin: 18px 0 4px; }
.block-title { margin: 18px 0 10px; font-size: 15px; font-weight: 600; color: var(--b-text, #1f2733); }
.step-block { border: 1px solid var(--b-border, #d4e2f4); border-radius: 8px; padding: 12px 14px; margin-bottom: 12px; background: #fff; }
.step-h { margin: 0 0 10px; font-size: 14px; font-weight: 600; color: var(--b-text, #1f2733); }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 14px; }
.grid2 .span2 { grid-column: 1 / -1; }
.field-label { display: block; font-size: 13px; margin-bottom: 4px; color: var(--b-muted, #5c6370); }
.req { color: #c0392b; margin-left: 2px; }
.gov-input { width: 100%; padding: 7px 10px; border-radius: 6px; border: 1px solid var(--b-border, #d4e2f4); box-sizing: border-box; font-size: 14px; }
.gov-input:disabled { background: #f4f6fa; color: #8a93a0; }
.gov-textarea { width: 100%; padding: 7px 10px; border-radius: 6px; border: 1px solid var(--b-border, #d4e2f4); box-sizing: border-box; font-size: 13px; resize: vertical; font-family: inherit; }
.gov-btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid transparent; margin-right: 8px; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.gov-btn-secondary { background: #fff; border-color: var(--b-border, #d4e2f4); }
.gov-btn-secondary:disabled { opacity: 0.5; cursor: not-allowed; }
.step-done { margin: 10px 0 0; font-size: 13px; color: #2c7a2c; }
.form-hint { margin: 8px 0 0; font-size: 12px; color: var(--b-muted, #5c6370); }
.reg-list { margin-bottom: 8px; }
.row-actions { white-space: nowrap; }
.row-actions-none { color: var(--b-muted, #8a93a0); }
.gov-btn-link { background: none; border: none; padding: 2px 6px; margin-right: 4px; color: var(--b-primary, #006be6); cursor: pointer; font-size: 13px; }
.gov-btn-link:hover:not(:disabled) { text-decoration: underline; }
.gov-btn-link:disabled { opacity: 0.5; cursor: not-allowed; }
.gov-btn-danger { color: #c0392b; }
</style>
