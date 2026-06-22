<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import { invokeActionStub, pushToast } from '@/composables/useActionStub';

// E3 Wave-2 F7 三引擎配置（收编为 B1.2 子页 /integration-admin/engines）：
// 审批流 / 表单 / 推荐 三 tab 共享「草稿 → 预览 → 入库」三步。
// 文案严守 R12（preflight 段 24 工程术语黑名单）：不出现 skill_id / manifest /
// config_change_class / audit_class / draft / preview / live 等纯工程词，
// 全部业务化为「能力 / 草稿 / 预览 / 入库 / 回退」等中文术语。

type EngineKey = 'approval_flow' | 'form_schema' | 'recommendation';

interface EnginePreset {
  title: string;
  intent: string;
  schemaCodeHint: string;
  schemaTitleHint: string;
}

interface EngineConfig {
  key: EngineKey;
  navTitle: string;
  heroTitle: string;
  heroHint: string;
  draftSkill: string;
  promoteSkill: string;
  revertSkill: string;
  commitSkill: string;
  schemaIdField: 'schema_id' | 'rule_id';
  schemaCodeLabel: string;
  titleLabel: string;
  intentLabel: string;
  examplePresets: EnginePreset[];
}

const ENGINES: EngineConfig[] = [
  {
    key: 'approval_flow',
    navTitle: '审批流',
    heroTitle: '审批流配置',
    heroHint: '一句话描述项目级审批流程 → 自动生成节点 / 选人规则 / 条件分支 → 管理员确认入库。',
    draftSkill: 'approval_flow.nl_draft',
    promoteSkill: 'approval_flow.schema.promote_to_preview',
    revertSkill: 'approval_flow.schema.revert_to_draft',
    commitSkill: 'approval_flow.schema.commit',
    schemaIdField: 'schema_id',
    schemaCodeLabel: '审批流编码',
    titleLabel: '审批流名称',
    intentLabel: '审批流意向',
    examplePresets: [
      {
        title: '标准 4 级审批流程',
        intent: '标准审批流程：编制→二级部门审→一级部门审→发布',
        schemaCodeHint: 'std_4level_v1',
        schemaTitleHint: '标准 4 级审批流',
      },
      {
        title: '简化 2 级审批',
        intent: '2 级审批流程',
        schemaCodeHint: 'simple_2level_v1',
        schemaTitleHint: '简化 2 级审批',
      },
    ],
  },
  {
    key: 'form_schema',
    navTitle: '申请表单',
    heroTitle: '申请表单配置',
    heroHint: '一句话描述表单字段意向 → 自动生成字段 / 校验 / 布局 → 管理员确认入库。',
    draftSkill: 'form_schema.nl_draft',
    promoteSkill: 'form_schema.promote_to_preview',
    revertSkill: 'form_schema.revert_to_draft',
    commitSkill: 'form_schema.commit',
    schemaIdField: 'schema_id',
    schemaCodeLabel: '表单编码',
    titleLabel: '表单名称',
    intentLabel: '字段意向',
    examplePresets: [
      {
        title: '完整 7 字段申请表',
        intent: '申请表单：姓名、身份证号、联系电话、单位、申请事由、申请日期、附件',
        schemaCodeHint: 'full_7field_v1',
        schemaTitleHint: '完整 7 字段申请表',
      },
      {
        title: '极简申请表',
        intent: '申请表：姓名、联系电话',
        schemaCodeHint: 'mini_form_v1',
        schemaTitleHint: '极简申请表',
      },
    ],
  },
  {
    key: 'recommendation',
    navTitle: '推荐规则',
    heroTitle: '推荐规则配置',
    heroHint: '管理员配置项目级推荐规则（关键词 / 分类 / 机构 / 高频 / 文本相似），命中后建议沿用已有目录。',
    draftSkill: '',
    promoteSkill: '',
    revertSkill: '',
    commitSkill: 'recommendation.rule.commit',
    schemaIdField: 'rule_id',
    schemaCodeLabel: '规则编码',
    titleLabel: '规则名称',
    intentLabel: '规则意向',
    examplePresets: [
      {
        title: '标准 5 条推荐规则',
        intent: '数据共享推荐规则：覆盖关键词 / 分类 / 机构 / 高频 / 文本相似 5 类',
        schemaCodeHint: 'std_5rules_v1',
        schemaTitleHint: '标准 5 条推荐规则',
      },
    ],
  },
];

const activeKey = ref<EngineKey>('approval_flow');
const tenantId = ref<string>('sd-default');
// 租户对用户显示为业务名（默认单租户场景 sd-default → 系统默认租户）；
// 原始 slug 保留在 title 悬浮里，payload 仍用 tenantId 原值（不污染后端契约）。
const tenantDisplay = computed(() =>
  tenantId.value === 'sd-default' ? '系统默认租户' : tenantId.value,
);
const schemaCodeInput = ref<Record<EngineKey, string>>({
  approval_flow: '',
  form_schema: '',
  recommendation: '',
});
const titleInput = ref<Record<EngineKey, string>>({
  approval_flow: '',
  form_schema: '',
  recommendation: '',
});
const intentInput = ref<Record<EngineKey, string>>({
  approval_flow: '',
  form_schema: '',
  recommendation: '',
});
const schemaIdInput = ref<Record<EngineKey, string>>({
  approval_flow: '',
  form_schema: '',
  recommendation: '',
});
const lastResultPayload = ref<Record<EngineKey, Record<string, unknown> | null>>({
  approval_flow: null,
  form_schema: null,
  recommendation: null,
});

function activeEngine() {
  return ENGINES.find((e) => e.key === activeKey.value) ?? ENGINES[0];
}

function applyPreset(preset: EnginePreset) {
  const k = activeKey.value;
  intentInput.value[k] = preset.intent;
  schemaCodeInput.value[k] = preset.schemaCodeHint;
  titleInput.value[k] = preset.schemaTitleHint;
}

// 进页面 / 切 tab 时若三字段全空则自动套用第一个示例 — 避免 placeholder
// 灰字被误认为已填值；用户手动改过的字段不会被覆盖（仅在 empty 时填）。
function autoFillIfEmpty() {
  const k = activeKey.value;
  const engine = activeEngine();
  const preset = engine.examplePresets[0];
  if (!preset) return;
  const empty =
    !schemaCodeInput.value[k].trim() &&
    !titleInput.value[k].trim() &&
    !intentInput.value[k].trim();
  if (empty) {
    intentInput.value[k] = preset.intent;
    schemaCodeInput.value[k] = preset.schemaCodeHint;
    titleInput.value[k] = preset.schemaTitleHint;
  }
}

onMounted(() => { autoFillIfEmpty(); });
watch(activeKey, () => { autoFillIfEmpty(); });

async function onGenerateDraft() {
  const engine = activeEngine();
  if (!engine.draftSkill) {
    pushToast({
      kind: 'info',
      title: '推荐规则暂以管理员直接编辑为主',
      detail: '请使用「入库生效」按提交规则草稿入库；意向解析能力下一版补齐。',
    });
    return;
  }
  const k = activeKey.value;
  const code = schemaCodeInput.value[k].trim();
  const title = titleInput.value[k].trim();
  const intent = intentInput.value[k].trim();
  if (!code || !title || !intent) {
    pushToast({ kind: 'warn', title: '请补齐三项', detail: `${engine.schemaCodeLabel} / ${engine.titleLabel} / ${engine.intentLabel}` });
    return;
  }
  // 出处（created_by）由后端从已 resolve 的真实 actor 取定，客户端不再硬串伪造身份。
  const payload: Record<string, unknown> = {
    tenant_id: tenantId.value,
    intent_text: intent,
  };
  if (k === 'approval_flow') {
    payload.schema_code = code;
    payload.title = title;
  } else if (k === 'form_schema') {
    payload.form_code = code;
    payload.title = title;
  }
  const res = await invokeActionStub({
    skillId: engine.draftSkill,
    payload,
    successTitle: '草稿已生成',
    pendingBackend: 'E3 三引擎',
  });
  if (res.ok && res.data && typeof res.data === 'object') {
    const data = res.data as Record<string, unknown>;
    const result = (data.result ?? {}) as Record<string, unknown>;
    lastResultPayload.value[k] = result;
    const newId = String(result.schema_id ?? result.rule_id ?? '');
    if (newId) {
      schemaIdInput.value[k] = newId;
    }
  }
}

async function onPromotePreview() {
  const engine = activeEngine();
  if (!engine.promoteSkill) {
    pushToast({ kind: 'info', title: '本引擎无独立预览步骤', detail: '请直接编辑后入库。' });
    return;
  }
  const k = activeKey.value;
  const sid = schemaIdInput.value[k].trim();
  if (!sid) {
    pushToast({ kind: 'warn', title: '缺少标识', detail: '请先生成草稿或填入已有草稿编号。' });
    return;
  }
  const payload: Record<string, unknown> = {
    tenant_id: tenantId.value,
    [engine.schemaIdField]: sid,
    confirmed: true,
  };
  const res = await invokeActionStub({
    skillId: engine.promoteSkill,
    payload,
    successTitle: '已提交预览',
    pendingBackend: 'E3 三引擎',
  });
  if (res.ok && res.data && typeof res.data === 'object') {
    lastResultPayload.value[k] = ((res.data as Record<string, unknown>).result ?? {}) as Record<string, unknown>;
  }
}

async function onRevertToDraft() {
  const engine = activeEngine();
  if (!engine.revertSkill) {
    pushToast({ kind: 'info', title: '本引擎无独立预览步骤', detail: '直接编辑后再入库即可。' });
    return;
  }
  const k = activeKey.value;
  const sid = schemaIdInput.value[k].trim();
  if (!sid) {
    pushToast({ kind: 'warn', title: '缺少标识', detail: '请先填入待回退的草稿编号。' });
    return;
  }
  const payload: Record<string, unknown> = {
    tenant_id: tenantId.value,
    [engine.schemaIdField]: sid,
    confirmed: true,
  };
  const res = await invokeActionStub({
    skillId: engine.revertSkill,
    payload,
    successTitle: '已回退到草稿',
    pendingBackend: 'E3 三引擎',
  });
  if (res.ok && res.data && typeof res.data === 'object') {
    lastResultPayload.value[k] = ((res.data as Record<string, unknown>).result ?? {}) as Record<string, unknown>;
  }
}

async function onCommitLive() {
  const engine = activeEngine();
  const k = activeKey.value;
  const sid = schemaIdInput.value[k].trim();
  // 推荐规则按设计无独立草稿步骤：UI 没 rule_id 时把 rule_code 一并传后端，
  // 后端按 (tenant, rule_code) 复用最新 payload 自动创建 v=max+1 并 commit。
  const isRecommendation = k === 'recommendation';
  if (!sid && !isRecommendation) {
    pushToast({ kind: 'warn', title: '缺少标识', detail: '请先生成或填入待入库的编号。' });
    return;
  }
  const payload: Record<string, unknown> = {
    tenant_id: tenantId.value,
    confirmed: true,
  };
  if (sid) {
    payload[engine.schemaIdField] = sid;
  } else if (isRecommendation) {
    const code = schemaCodeInput.value[k].trim();
    if (!code) {
      pushToast({ kind: 'warn', title: '缺少标识', detail: '请填入规则编码（或点示例预填）。' });
      return;
    }
    payload.rule_code = code;
    payload.title = titleInput.value[k].trim();
    payload.draft_source_text = intentInput.value[k].trim();
  }
  const res = await invokeActionStub({
    skillId: engine.commitSkill,
    payload,
    successTitle: '已入库生效',
    pendingBackend: 'E3 三引擎',
  });
  if (res.ok && res.data && typeof res.data === 'object') {
    const result = ((res.data as Record<string, unknown>).result ?? {}) as Record<string, unknown>;
    lastResultPayload.value[k] = result;
    const newId = String(result.rule_id ?? result.schema_id ?? '');
    if (newId && !sid) {
      schemaIdInput.value[k] = newId;
    }
  }
}

function lastResultText(): string {
  const r = lastResultPayload.value[activeKey.value];
  if (!r) return '尚无最近一次操作结果。';
  return JSON.stringify(r, null, 2);
}
</script>

<template>
  <main class="focus-page">
    <section class="panel panel-stack">
      <PageFocusHeader
        title="流程与表单配置"
        meta="审批流 · 申请表单 · 推荐规则（草稿→预览→入库）"
      />

      <p class="wave2-banner" role="note">
        本页配置处于「草稿 → 预览 → 入库」流程，正式启用前可反复预览修改。
      </p>

      <section class="focus-section">
      <header class="tab-row">
        <button
          v-for="engine in ENGINES"
          :key="engine.key"
          type="button"
          class="tab-btn"
          :class="{ 'tab-active': engine.key === activeKey }"
          @click="activeKey = engine.key"
        >
          {{ engine.navTitle }}
        </button>
      </header>

      <div class="engine-body">
        <p class="engine-hint">{{ activeEngine().heroHint }}</p>

        <div class="preset-row">
          <span class="preset-kicker">示例</span>
          <button
            v-for="preset in activeEngine().examplePresets"
            :key="preset.title"
            type="button"
            class="preset-btn"
            @click="applyPreset(preset)"
          >
            {{ preset.title }}
          </button>
        </div>

        <div class="form-grid">
          <label class="form-row">
            <span class="form-label">租户</span>
            <input
              :value="tenantDisplay"
              type="text"
              class="form-input"
              readonly
              :title="tenantId"
            />
          </label>
          <label class="form-row">
            <span class="form-label">{{ activeEngine().schemaCodeLabel }}</span>
            <input
              v-model="schemaCodeInput[activeKey]"
              type="text"
              class="form-input"
              placeholder="输入唯一编码，或点上方示例预填"
            />
          </label>
          <label class="form-row">
            <span class="form-label">{{ activeEngine().titleLabel }}</span>
            <input
              v-model="titleInput[activeKey]"
              type="text"
              class="form-input"
              placeholder="输入名称，或点上方示例预填"
            />
          </label>
          <label class="form-row form-row-tall">
            <span class="form-label">{{ activeEngine().intentLabel }}</span>
            <textarea
              v-model="intentInput[activeKey]"
              class="form-input form-textarea"
              rows="3"
              placeholder="一句话描述意向，或点上方示例预填"
            />
          </label>
          <label class="form-row">
            <span class="form-label">当前编号</span>
            <input
              v-model="schemaIdInput[activeKey]"
              type="text"
              class="form-input"
              placeholder="生成草稿后自动填入；也可直接填入已有编号"
            />
          </label>
        </div>

        <p v-if="!activeEngine().draftSkill" class="engine-direct-edit-hint">
          本引擎按设计仅支持「管理员直接编辑后入库」 — 三步流程的「草稿 / 预览 / 回退」对本引擎不适用，请直接点「入库生效」。
        </p>
        <div class="action-row">
          <button
            v-if="activeEngine().draftSkill"
            type="button"
            class="gov-btn gov-btn-primary"
            @click="onGenerateDraft"
          >生成草稿</button>
          <button
            v-if="activeEngine().promoteSkill"
            type="button"
            class="gov-btn"
            @click="onPromotePreview"
          >提交预览</button>
          <button
            v-if="activeEngine().revertSkill"
            type="button"
            class="gov-btn"
            @click="onRevertToDraft"
          >回退到草稿</button>
          <button type="button" class="gov-btn gov-btn-strong" @click="onCommitLive">入库生效</button>
        </div>

        <div class="result-box">
          <header>
            <h3 class="result-title">最近一次操作结果</h3>
            <p class="result-subtitle">仅供管理员核对；正式审阅请走「合规与运营」页面的审计回放。</p>
          </header>
          <pre class="result-pre">{{ lastResultText() }}</pre>
        </div>
      </div>
      </section>
    </section>
  </main>
</template>

<style scoped>
.engine-hint { margin: 0 0 14px; font-size: 14px; line-height: 1.6; color: var(--b-muted, #5c6370); }
.engine-direct-edit-hint {
  margin: 8px 0 12px; padding: 8px 12px; font-size: 13px; line-height: 1.5;
  color: var(--b-text, #1f2937);
  background: #fff7e6; border: 1px solid #ffd591; border-radius: 6px;
}
.tab-row { display: flex; gap: 8px; margin: 0 0 16px; padding-bottom: 12px; border-bottom: 1px solid var(--b-border, #d4e2f4); }
.tab-btn {
  padding: 8px 16px; border: none; background: transparent; cursor: pointer; font-size: 14px;
  color: var(--b-muted, #5c6370); border-bottom: 2px solid transparent;
}
.tab-active { color: var(--b-primary, #006be6); border-bottom-color: var(--b-primary, #006be6); font-weight: 600; }
.engine-body { display: grid; gap: 16px; }
.engine-meta h2 { margin: 0 0 6px; }
.engine-meta p { margin: 0; color: var(--b-muted, #5c6370); font-size: 13px; }
.preset-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.preset-kicker { font-size: 12px; color: var(--b-muted, #5c6370); }
.preset-btn {
  padding: 4px 10px; border: 1px solid var(--b-border, #d4e2f4); background: var(--b-bg-subtle, #e8f2fc);
  border-radius: 999px; cursor: pointer; font-size: 12px;
}
.form-grid { display: grid; gap: 12px; grid-template-columns: 1fr 1fr; }
.form-row { display: flex; flex-direction: column; gap: 4px; }
.form-row-tall { grid-column: span 2; }
.form-label { font-size: 12px; color: var(--b-muted, #5c6370); }
.form-input {
  padding: 8px 10px; border: 1px solid var(--b-border, #d4e2f4); border-radius: 6px;
  font-size: 13px; background: #fff;
}
.form-textarea { resize: vertical; font-family: inherit; }
.action-row { display: flex; gap: 8px; }
.gov-btn {
  padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer;
  border: 1px solid var(--b-border, #d4e2f4); background: #fff;
}
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; border-color: var(--b-primary, #006be6); }
.gov-btn-strong { background: #f0a800; color: #fff; border-color: #f0a800; }
.result-box {
  background: var(--b-bg-subtle, #f3f8ff); padding: 12px; border-radius: 6px; border: 1px solid var(--b-border, #d4e2f4);
}
.result-title { margin: 0 0 4px; font-size: 13px; }
.result-subtitle { margin: 0 0 8px; font-size: 11px; color: var(--b-muted, #5c6370); }
.result-pre {
  margin: 0; padding: 8px; background: #fff; border-radius: 4px; font-size: 11px; color: #2a3a52;
  max-height: 180px; overflow: auto; white-space: pre-wrap;
}
.wave2-banner {
  margin: 0 0 12px; padding: 10px 12px; border-radius: 6px;
  background: #fff8e6; border: 1px solid #f0d080; font-size: 13px; color: #6b4e00;
}
</style>
