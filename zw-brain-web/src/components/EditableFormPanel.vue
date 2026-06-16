<script setup lang="ts">
/** 表单填报可编辑面板（form-autofill）：四态渲染 + 人原地修订（改即锁）+ 枚举带出。
 *
 *  - 待填(empty)        → 普通输入框，灰 pill「待填写」
 *  - AI建议(ai_suggested)→ 琥珀输入框，橙 pill「AI建议·待确认」（人手动提交=担责）
 *  - 自动带出(derived)   → 只读，蓝 pill「自动带出」（派生权威，不可手填）
 *  - 已填(human)        → 输入框，绿 pill「已填写」+ 锁标（此后 autofill/AI 不覆盖）
 *
 *  人改某字段 → request.field.update → 标 human+locked 并重跑派生（如改责任单位→区划自动带出）。
 */
import { onMounted, ref, watch } from 'vue';
import {
  type FormField,
  type RefOption,
  aiSuggestDraft,
  fetchDictOptions,
  sourceTone,
  updateField,
} from '@/lib/formFields';
import ReferencePicker from '@/components/ReferencePicker.vue';
import { pushToast } from '@/composables/useActionStub';
import { invalidateSnapshot } from '@/composables/useSnapshot';
import { getProductRole } from '@/composables/useProductRole';

const props = defineProps<{ requestId: string; modelFields: FormField[] }>();
const productRole = getProductRole();

const fields = ref<FormField[]>([]);
const dictOptions = ref<Record<string, RefOption[]>>({});
const saving = ref<string>('');

watch(
  () => props.modelFields,
  (next) => {
    fields.value = (next ?? []).map((f) => ({ ...f }));
  },
  { immediate: true, deep: true },
);

function currentValue(key: string): string {
  return String(fields.value.find((f) => f.key === key)?.value ?? '');
}

function nameFor(key: string): string {
  // 派生名称字段（organ_name/region_name）已由服务端带出，用作选择器回显名。
  const nameKey = key === 'organ_code' ? 'organ_name' : key === 'region_code' ? 'region_name' : '';
  return nameKey ? currentValue(nameKey) : '';
}

// 整句型字段（用途/理由/范围）用多行 textarea，单行框写不下一句话。
// 后端 kind 统一为 text（不区分长短），故按 key 在前端判定。
const MULTILINE_KEYS = new Set(['purpose', 'use_reason', 'scope']);
function isMultiline(f: FormField): boolean {
  return f.kind === 'text' && MULTILINE_KEYS.has(f.key);
}

onMounted(async () => {
  // 枚举字段 options（pub_dict 字典带出）；机构/区划选项由 ReferencePicker 自取（搜索/下钻）。
  for (const f of fields.value) {
    if (f.kind === 'enum' && f.dictType && !dictOptions.value[f.dictType]) {
      try {
        dictOptions.value[f.dictType] = await fetchDictOptions(f.dictType);
      } catch {
        dictOptions.value[f.dictType] = [];
      }
    }
  }
});

const aiSuggesting = ref(false);
async function aiSuggest(): Promise<void> {
  aiSuggesting.value = true;
  try {
    const next = await aiSuggestDraft(props.requestId, productRole.value);
    if (next.length) fields.value = next.map((f) => ({ ...f }));
    invalidateSnapshot();
    pushToast({ kind: 'ok', title: 'AI 已给出建议', detail: '空字段已填入「AI建议·待确认」，请逐项核对修订后再提交。' });
  } catch (e) {
    pushToast({ kind: 'error', title: 'AI 建议失败', detail: String(e) });
  } finally {
    aiSuggesting.value = false;
  }
}

async function commit(field: FormField, raw: string): Promise<void> {
  const value = String(raw ?? '');
  if (value === field.value) return;
  saving.value = field.key;
  try {
    const next = await updateField(props.requestId, field.key, value, productRole.value);
    if (next.length) fields.value = next.map((f) => ({ ...f }));
    invalidateSnapshot();
    pushToast({ kind: 'ok', title: '已保存', detail: `「${field.label}」已记为人工填写并锁定。` });
  } catch (e) {
    pushToast({ kind: 'error', title: '保存失败', detail: String(e) });
  } finally {
    saving.value = '';
  }
}
</script>

<template>
  <section class="detail-block ff-panel">
    <header class="detail-block-head ff-head">
      <div>
        <h2 class="detail-block-title">申请表单</h2>
        <p class="detail-block-sub">
          字段已自动带出，逐项核对修订即可（改过即锁定）；空字段可用 AI 建议填充，确认后再提交。
        </p>
      </div>
      <button
        type="button"
        class="ff-ai-btn"
        data-testid="ff-ai-suggest"
        :disabled="aiSuggesting"
        @click="aiSuggest"
      >
        {{ aiSuggesting ? 'AI 生成中…' : '✨ AI 建议填充' }}
      </button>
    </header>
    <dl class="detail-list ff-list">
      <template v-for="f in fields" :key="f.key">
        <dt>{{ f.label }}</dt>
        <dd>
          <div class="ff-field">
          <!-- 派生：只读自动带出 -->
          <template v-if="!f.editable">
            <span class="detail-value ff-readonly">{{ f.value || '—' }}</span>
          </template>
          <!-- 枚举：下拉 -->
          <template v-else-if="f.kind === 'enum' && f.dictType">
            <select
              class="ff-input"
              :data-testid="`ff-${f.key}`"
              :disabled="saving === f.key"
              :value="f.value"
              @change="commit(f, ($event.target as HTMLSelectElement).value)"
            >
              <option value="">请选择</option>
              <option v-for="o in dictOptions[f.dictType] || []" :key="o.code" :value="o.code">
                {{ o.name }}
              </option>
            </select>
          </template>
          <!-- 机构：搜索分页选择器（18750 机构）；选中后服务端确定性带出名称+所属区划 -->
          <template v-else-if="f.kind === 'org'">
            <ReferencePicker
              mode="organ"
              :model-value="f.value"
              :display-name="nameFor(f.key)"
              :region-code="currentValue('region_code')"
              :disabled="saving === f.key"
              :testid="`ff-${f.key}`"
              @update:model-value="(code: string) => commit(f, code)"
            />
          </template>
          <!-- 区划：逐级下钻选择器（省→市→县…，面包屑回退） -->
          <template v-else-if="f.kind === 'region'">
            <ReferencePicker
              mode="region"
              :model-value="f.value"
              :display-name="nameFor(f.key)"
              :disabled="saving === f.key"
              :testid="`ff-${f.key}`"
              @update:model-value="(code: string) => commit(f, code)"
            />
          </template>
          <!-- 整句型文本（用途/理由/范围）：多行 textarea -->
          <template v-else-if="isMultiline(f)">
            <textarea
              class="ff-input ff-textarea"
              :data-testid="`ff-${f.key}`"
              :disabled="saving === f.key"
              :value="f.value"
              :placeholder="f.source === 'empty' ? '请填写' : ''"
              rows="3"
              @change="commit(f, ($event.target as HTMLTextAreaElement).value)"
            />
          </template>
          <!-- 文本 / 机构码 / 区划码：单行输入框（失焦提交，触发带出/锁定） -->
          <template v-else>
            <input
              class="ff-input"
              :data-testid="`ff-${f.key}`"
              :disabled="saving === f.key"
              :value="f.value"
              :placeholder="f.source === 'empty' ? '请填写' : ''"
              @change="commit(f, ($event.target as HTMLInputElement).value)"
            />
          </template>
          <span class="ff-pill" :class="sourceTone(f.source)" :data-testid="`ff-pill-${f.key}`">
            {{ f.stateLabel }}
          </span>
          <span v-if="f.locked" class="ff-lock" title="人工填写已锁定">🔒</span>
          </div>
        </dd>
      </template>
    </dl>
  </section>
</template>

<style scoped>
.ff-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.ff-ai-btn {
  flex: 0 0 auto;
  padding: 6px 14px;
  border-radius: 6px;
  border: 1px solid var(--b-primary, #006be6);
  background: #fff;
  color: var(--b-primary, #006be6);
  font-size: 13px;
  cursor: pointer;
  white-space: nowrap;
}
.ff-ai-btn:hover:not(:disabled) { background: var(--b-primary, #006be6); color: #fff; }
.ff-ai-btn:disabled { opacity: 0.6; cursor: not-allowed; }
/* 全局 .detail-list dd 是 flex-direction:column（只读 DetailPanel 用，值在上、副文本在下）。
   表单复用了同一栅格，若把控件直接放进列向 dd，控件的 flex-basis 会被当成「行高」
   —— .ff-input 的 220px 基线会把每个输入框撑成 220px 高的巨框、状态 pill 被挤到下方漂浮。
   解法：把「控件 + 状态 pill + 锁」收进一行 .ff-field，让列向 dd 只含这一个子元素，
   控件回到自然行高、pill 与控件同行。 */
.ff-field {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  width: 100%;
}
.ff-input {
  flex: 0 1 360px;
  min-width: 200px;
  max-width: 360px;
  height: 32px;
  box-sizing: border-box;
  padding: 5px 9px;
  border: 1px solid var(--b-border, #d4e2f4);
  border-radius: 6px;
  font-size: 13px;
}
select.ff-input { padding-right: 6px; cursor: pointer; }
.ff-list :deep(.ref-picker) { flex: 0 1 360px; }
.ff-input:disabled { background: #f4f7fb; }
/* 整句型字段：多行 textarea，比单行框宽一点、可纵向拉伸。 */
.ff-textarea {
  flex: 0 1 420px;
  max-width: 420px;
  height: auto;
  min-height: 66px;
  padding: 6px 9px;
  line-height: 1.5;
  resize: vertical;
  font-family: inherit;
}
/* 标签右对齐、统一冒号，控件左缘对齐成一条竖线。 */
.ff-list dt {
  text-align: right;
}
.ff-list dt::after {
  content: '：';
}
.ff-readonly { color: var(--b-neutral-text, #1a1d21); font-weight: 500; }
.ff-pill {
  font-size: 12px;
  padding: 1px 8px;
  border-radius: 10px;
  white-space: nowrap;
}
.ff-human { background: #e8f7ee; color: #1a7f37; }
.ff-derived { background: #e7f0fe; color: #0b5cad; }
.ff-ai { background: #fff4e5; color: #b25e00; }
.ff-empty { background: #f0f1f3; color: #6b7280; }
.ff-lock { font-size: 12px; }
</style>
