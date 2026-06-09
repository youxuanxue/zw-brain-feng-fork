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

const props = defineProps<{ requestId: string; modelFields: FormField[] }>();

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
    const next = await aiSuggestDraft(props.requestId);
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
    const next = await updateField(props.requestId, field.key, value);
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
          系统已按机构/区划/字典自动带出；可点「AI 建议填充」对空字段给出待确认建议。逐项核对修订即可，
          改过的字段会锁定、不再被自动覆盖；AI 建议永不自动提交，需你确认提交。
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
          <!-- 文本 / 机构码 / 区划码：输入框（失焦提交，触发带出/锁定） -->
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
.ff-list dd { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ff-input {
  flex: 1 1 220px;
  min-width: 180px;
  padding: 5px 9px;
  border: 1px solid var(--b-border, #d4e2f4);
  border-radius: 6px;
  font-size: 13px;
}
.ff-input:disabled { background: #f4f7fb; }
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
