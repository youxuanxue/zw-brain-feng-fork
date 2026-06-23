<script setup lang="ts">
import { computed, ref } from 'vue';
import { useNLAccelerator, type StructuredAction } from '@/composables/useNLAccelerator';

// F7 通用 NL 加速器面板：嵌到 P2/P3/B1.1/B1.2 主页面 hero 右侧。
//   - 默认折叠（icon 按钮显示）；展开后 380px 侧抽屉
//   - input + 3-5 preset chip
//   - submit → useNLAccelerator.parse() → StructuredAction[] 渲染
//   - 失败回落 fixture / pending 提示，反约束「不替代主页面 + 结构化输出 + 失败可解释」

const props = defineProps<{
  pageAnchor: string;
  presets: string[];
}>();

const emit = defineEmits<{
  (e: 'action', action: StructuredAction): void;
}>();

const DEFAULT_COPY = {
  label: '检索助手',
  hint: '输入一句话，解析后会自动生成可执行动作。',
  placeholder: '例如：查省营商环境相关数据',
};

const COPY_BY_ANCHOR: Record<string, typeof DEFAULT_COPY> = {
  P2: {
    label: '找数助手',
    hint: '输入一句找数诉求，解析后会自动填入搜索并展示结果。',
    placeholder: '例如：查省营商环境相关数据',
  },
  P3: {
    label: '申请助手',
    hint: '输入一句申请或审批诉求，生成可执行建议。',
    placeholder: '例如：帮我草拟停车场数据申请',
  },
  'B1.1': {
    label: '审计助手',
    hint: '输入一句审计诉求，定位异常、统计或回放证据链。',
    placeholder: '例如：查本周异常审批热点',
  },
  'B1.2': {
    label: '接入助手',
    hint: '输入一句接入诉求，定位外部 Agent 注册与安全检查动作。',
    placeholder: '例如：检查外部 Agent 注册材料',
  },
};

const panelCopy = computed(() => COPY_BY_ANCHOR[props.pageAnchor] ?? DEFAULT_COPY);
const panelTitle = computed(() => panelCopy.value.label);

const open = ref(false);
const query = ref('');
const { result, source, loading, error, parse, clear } = useNLAccelerator(props.pageAnchor);

function toggle() {
  open.value = !open.value;
  if (!open.value) {
    query.value = '';
    clear();
  }
}

function autoApplyPrimaryAction() {
  const primary = result.value?.actions.find(
    (a) =>
      (a.kind === 'filter' && a.payload && (a.payload.query || a.payload.zone)) ||
      a.kind === 'navigate',
  );
  if (primary) triggerAction(primary);
}

async function submit() {
  const q = query.value.trim();
  if (!q) return;
  await parse(q);
  autoApplyPrimaryAction();
}

function applyPreset(p: string) {
  query.value = p;
  void parse(p).then(autoApplyPrimaryAction);
}

function triggerAction(action: StructuredAction) {
  emit('action', action);
  if (action.kind === 'navigate' && action.target) {
    window.location.hash = action.target;
  }
}
</script>

<template>
  <div class="nl-accelerator" :class="{ 'is-open': open }">
    <button
      type="button"
      class="nl-trigger"
      :title="open ? `收起${panelTitle}` : `展开${panelTitle}`"
      @click="toggle"
    >
      <span aria-hidden="true">{{ open ? '×' : '⌘' }}</span>
      <span class="nl-trigger-text">{{ panelTitle }}</span>
    </button>

    <aside v-if="open" class="nl-drawer" role="complementary" :aria-label="panelTitle">
      <header class="nl-head">
        <strong>{{ panelTitle }}</strong>
        <p class="nl-hint">{{ panelCopy.hint }}</p>
      </header>

      <form class="nl-form" @submit.prevent="submit">
        <label class="sr-only" :for="`nl-input-${pageAnchor}`">自然语言输入</label>
        <input
          :id="`nl-input-${pageAnchor}`"
          v-model="query"
          type="text"
          class="nl-input"
          :placeholder="panelCopy.placeholder"
          autocomplete="off"
        />
        <button type="submit" class="nl-submit" :disabled="loading">{{ loading ? '解析中…' : '解析' }}</button>
      </form>

      <div class="nl-presets">
        <span class="nl-preset-label">快捷：</span>
        <button
          v-for="p in presets"
          :key="p"
          type="button"
          class="nl-chip"
          @click="applyPreset(p)"
        >{{ p }}</button>
      </div>

      <section v-if="result" class="nl-result">
        <div class="nl-source">
          <template v-if="source === 'live'">
            <span class="nl-tag nl-tag-ok">真实后端</span>
          </template>
          <template v-else-if="source === 'fixture'">
            <span class="nl-tag nl-tag-warn">离线建议（后端暂不可用）</span>
          </template>
          <template v-else>
            <span class="nl-tag nl-tag-pending">解析未命中</span>
          </template>
        </div>
        <p class="nl-summary">{{ result.summary }}</p>
        <ul v-if="result.actions.length" class="nl-actions">
          <li v-for="(a, i) in result.actions" :key="i">
            <button type="button" class="nl-action-btn" :data-kind="a.kind" @click="triggerAction(a)">
              <strong>{{ a.label }}</strong>
              <em v-if="a.detail">{{ a.detail }}</em>
            </button>
          </li>
        </ul>
        <p v-else class="nl-fallback">未解析出可执行动作；请使用页面上的按钮直接操作。</p>
      </section>
      <div v-else-if="error" class="nl-error">
        加速器调用出错：{{ error }}（已尝试离线建议）
      </div>
    </aside>
  </div>
</template>

<style scoped>
.nl-accelerator { position: relative; display: inline-block; }
.nl-trigger {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 12px; border-radius: 999px;
  background: var(--b-bg-subtle, #e8f2fc); color: var(--b-primary, #006be6);
  border: 1px solid var(--b-border, #d4e2f4); cursor: pointer; font-size: 13px;
}
.nl-trigger:hover { background: #d8eafc; }
.nl-trigger-text { font-weight: 600; }
.nl-drawer {
  position: absolute; top: 40px; right: 0; width: 380px;
  background: #fff; border: 1px solid var(--b-border, #d4e2f4); border-radius: 12px;
  box-shadow: 0 12px 24px rgba(0, 75, 168, 0.08); padding: 16px; z-index: 50;
  display: grid; gap: 12px;
}
.nl-head strong { font-size: 14px; }
.nl-hint { font-size: 12px; color: var(--b-muted, #5c6370); margin: 4px 0 0; line-height: 1.5; }
.nl-form { display: flex; gap: 6px; }
.nl-input { flex: 1; padding: 6px 10px; border: 1px solid var(--b-border, #d4e2f4); border-radius: 6px; font-size: 13px; }
.nl-submit {
  padding: 6px 14px; border-radius: 6px; background: var(--b-primary, #006be6);
  color: #fff; border: 0; cursor: pointer; font-size: 13px;
}
.nl-submit:disabled { background: #9bbedd; cursor: wait; }
.nl-presets { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.nl-preset-label { font-size: 12px; color: var(--b-muted, #5c6370); }
.nl-chip {
  font-size: 12px; padding: 4px 10px; border-radius: 999px;
  background: var(--b-bg-page, #f2f7fd); border: 1px solid var(--b-border, #d4e2f4);
  cursor: pointer; color: var(--b-neutral-text, #1a1d21);
}
.nl-chip:hover { background: var(--b-bg-subtle, #e8f2fc); }
.nl-result { display: grid; gap: 8px; }
.nl-tag { font-size: 11px; padding: 2px 8px; border-radius: 999px; }
.nl-tag-ok      { background: #effaee; color: #1f5e1f; border: 1px solid #9ad29a; }
.nl-tag-warn    { background: #fff8e6; color: #6b4f00; border: 1px solid #f0c674; }
.nl-tag-pending { background: var(--b-bg-page, #f2f7fd); color: var(--b-muted, #5c6370); border: 1px solid var(--b-border, #d4e2f4); }
.nl-summary { font-size: 13px; margin: 0; line-height: 1.5; }
.nl-actions { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }
.nl-action-btn {
  display: block; width: 100%; text-align: left;
  padding: 8px 10px; border-radius: 6px;
  background: var(--b-bg-page, #f2f7fd); border: 1px solid var(--b-border, #d4e2f4);
  cursor: pointer; font-size: 13px; color: inherit;
}
.nl-action-btn:hover { background: var(--b-bg-subtle, #e8f2fc); }
.nl-action-btn strong { display: block; font-weight: 600; }
.nl-action-btn em { display: block; font-style: normal; font-size: 12px; color: var(--b-muted, #5c6370); margin-top: 2px; }
.nl-fallback { font-size: 12px; color: var(--b-muted, #5c6370); margin: 0; }
.nl-error { font-size: 12px; color: #7a1a1a; }
.sr-only {
  position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
  overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0;
}
</style>
