<script setup lang="ts">
import { ref } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import NLAcceleratorPanel from '@/components/NLAcceleratorPanel.vue';
import { invokeActionStub, pushToast } from '@/composables/useActionStub';
import type { StructuredAction } from '@/composables/useNLAccelerator';

// E3 Wave-2 F7 三引擎配置中心：审批流 / 表单 / 推荐 三 tab 共享「草稿 → 预览 → 入库」三步。
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
        title: '鞍山 4 级审批流程',
        intent: '鞍山审批流程：编制→二级部门审→一级部门审→发布',
        schemaCodeHint: 'anshan_4level_v1',
        schemaTitleHint: '鞍山 4 级审批流',
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
        title: '四川 7 字段申请表',
        intent: '四川申请表单：姓名、身份证号、联系电话、单位、申请事由、申请日期、附件',
        schemaCodeHint: 'sichuan_7field_v1',
        schemaTitleHint: '四川 7 字段申请表',
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
    heroHint: '管理员配置项目级推荐规则（关键词 / 分类 / 机构 / 高频 / 文本相似），命中后建议复用已有目录。',
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
        title: '荆州 5 条推荐规则',
        intent: '荆州数据共享推荐规则：覆盖关键词 / 分类 / 机构 / 高频 / 文本相似 5 类',
        schemaCodeHint: 'jinzhou_5rules_v1',
        schemaTitleHint: '荆州 5 条推荐规则',
      },
    ],
  },
];

const activeKey = ref<EngineKey>('approval_flow');
const tenantId = ref<string>('sd-default');
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

const NL_PRESETS_B13 = ENGINES.flatMap((e) => e.examplePresets.map((p) => p.title));

function consumeNLAction(action: StructuredAction) {
  if (action.kind === 'invoke' && action.target) {
    void invokeActionStub({ skillId: action.target, payload: action.payload, successTitle: action.label });
  } else if (action.kind === 'filter' || action.kind === 'draft') {
    pushToast({ kind: 'info', title: '已应用', detail: action.label });
  }
}

const headerLinks = [
  { label: '合规与运营', href: '#/compliance-ops' },
  { label: '平台接入', href: '#/integration-admin' },
];

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
  const payload: Record<string, unknown> = {
    tenant_id: tenantId.value,
    intent_text: intent,
    created_by: 'user:gov:ROLE_ORGAN_MANAGER:webui',
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
    role: 'ROLE_ORGAN_MANAGER',
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
    role: 'ROLE_ORGAN_MANAGER',
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
    role: 'ROLE_ORGAN_MANAGER',
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
  if (!sid) {
    pushToast({ kind: 'warn', title: '缺少标识', detail: '请先生成或填入待入库的编号。' });
    return;
  }
  const payload: Record<string, unknown> = {
    tenant_id: tenantId.value,
    [engine.schemaIdField]: sid,
    confirmed: true,
  };
  const res = await invokeActionStub({
    skillId: engine.commitSkill,
    payload,
    successTitle: '已入库生效',
    role: 'ROLE_ORGAN_MANAGER',
    pendingBackend: 'E3 三引擎',
  });
  if (res.ok && res.data && typeof res.data === 'object') {
    lastResultPayload.value[k] = ((res.data as Record<string, unknown>).result ?? {}) as Record<string, unknown>;
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
        title="三引擎配置"
        meta="审批流 · 申请表单 · 推荐规则（草稿→预览→入库）"
        :links="headerLinks"
      >
        <template #aside>
          <NLAcceleratorPanel page-anchor="B1.3" :presets="NL_PRESETS_B13" @action="consumeNLAction" />
        </template>
      </PageFocusHeader>

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
            <input v-model="tenantId" type="text" class="form-input" />
          </label>
          <label class="form-row">
            <span class="form-label">{{ activeEngine().schemaCodeLabel }}</span>
            <input
              v-model="schemaCodeInput[activeKey]"
              type="text"
              class="form-input"
              :placeholder="activeEngine().examplePresets[0]?.schemaCodeHint"
            />
          </label>
          <label class="form-row">
            <span class="form-label">{{ activeEngine().titleLabel }}</span>
            <input
              v-model="titleInput[activeKey]"
              type="text"
              class="form-input"
              :placeholder="activeEngine().examplePresets[0]?.schemaTitleHint"
            />
          </label>
          <label class="form-row form-row-tall">
            <span class="form-label">{{ activeEngine().intentLabel }}</span>
            <textarea
              v-model="intentInput[activeKey]"
              class="form-input form-textarea"
              rows="3"
              :placeholder="activeEngine().examplePresets[0]?.intent"
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

        <div class="action-row">
          <button type="button" class="gov-btn gov-btn-primary" @click="onGenerateDraft">生成草稿</button>
          <button type="button" class="gov-btn" @click="onPromotePreview">提交预览</button>
          <button type="button" class="gov-btn" @click="onRevertToDraft">回退到草稿</button>
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
</style>
