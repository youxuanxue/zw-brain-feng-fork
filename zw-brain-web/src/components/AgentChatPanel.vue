<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { useAgentChat } from '@/composables/useAgentChat';

// 通用内联 Agent 对话面板。智能体工作台、找数页副驾共用本组件，只传 agentId 等 props，
// 不带悬浮球外壳（由所在页面/容器决定布局）。对话引擎复用 useAgentChat。
// agentId 固定于实例：切换应用请由父组件用 :key="agentId" 重挂载本组件。
const props = withDefaults(
  defineProps<{
    agentId: string;
    title?: string;
    hint?: string;
    placeholder?: string;
    presets?: string[];
    roleHint?: string;
    requestPrefix?: string;
    runtimeEnabled?: boolean;
    // 本应用可用的岗位中文名（来自 /agents 的 allowed_role_names）；403 文案据此列出可切换岗位。
    allowedRoleNames?: string[];
  }>(),
  {
    title: '智能助手',
    hint: '',
    placeholder: '输入你的问题…',
    presets: () => [],
    roleHint: '',
    requestPrefix: 'UI-AGENT',
    runtimeEnabled: undefined,
    allowedRoleNames: () => [],
  },
);

const { messages, loading, error, runtimeEnabled: chatRuntimeEnabled, probeRuntime, ask, stop } = useAgentChat(props.agentId, {
  requestPrefix: props.requestPrefix,
  logPrefix: 'AgentChat',
  allowedRoleNames: props.allowedRoleNames,
});

const draft = ref('');
const canAsk = computed(() => props.runtimeEnabled !== false && chatRuntimeEnabled.value !== false);
const showUnavailable = computed(() => props.runtimeEnabled === false || chatRuntimeEnabled.value === false);

async function submit() {
  const q = draft.value.trim();
  if (!q) return;
  draft.value = '';
  await ask(q);
}
function applyPreset(text: string) {
  draft.value = '';
  void ask(text);
}

onMounted(() => {
  void probeRuntime();
});
// 卸载（返回应用列表 / 切换应用 / 离开页面）即停掉后台轮询，避免游离请求循环。
onUnmounted(() => {
  stop();
});
</script>

<template>
  <section class="achat">
    <header v-if="title || hint || roleHint" class="achat-head">
      <strong class="achat-title">{{ title }}</strong>
      <p v-if="hint" class="achat-hint">{{ hint }}</p>
      <p v-if="roleHint" class="achat-rolehint">{{ roleHint }}</p>
      <p v-if="showUnavailable" class="achat-warn">
        当前助手暂不可用。
      </p>
    </header>

    <div class="achat-log" aria-live="polite">
      <p v-if="!messages.length" class="achat-empty">输入问题开始对话，或点下方快捷问题。</p>
      <article
        v-for="(msg, idx) in messages"
        :key="idx"
        class="achat-msg"
        :data-role="msg.role"
      >
        <span class="achat-msg-label">{{ msg.role === 'user' ? '我' : '助手' }}</span>
        <pre class="achat-msg-body">{{ msg.text }}</pre>
      </article>
    </div>

    <form class="achat-form" @submit.prevent="submit">
      <label class="sr-only" :for="`achat-input-${agentId}`">问题</label>
      <textarea
        :id="`achat-input-${agentId}`"
        v-model="draft"
        class="achat-input"
        rows="3"
        :placeholder="placeholder"
        :disabled="loading || !canAsk"
      />
      <button type="submit" class="achat-submit" :disabled="loading || !canAsk">
        {{ loading ? '思考中…' : '发送' }}
      </button>
    </form>

    <div v-if="presets.length" class="achat-presets">
      <span class="achat-preset-label">快捷：</span>
      <button
        v-for="p in presets"
        :key="p"
        type="button"
        class="achat-chip"
        :disabled="loading || !canAsk"
        @click="applyPreset(p)"
      >{{ p }}</button>
    </div>

    <p v-if="error" class="achat-error">{{ error }}</p>
  </section>
</template>

<style scoped>
.achat {
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100%;
  min-height: 320px;
}
.achat-title {
  font-size: 15px;
  color: #0f3d7a;
}
.achat-hint {
  margin: 4px 0 0;
  font-size: 12px;
  color: #5a6b7d;
}
.achat-rolehint {
  margin: 4px 0 0;
  font-size: 12px;
  color: #8a5a00;
}
.achat-warn {
  margin: 8px 0 0;
  font-size: 12px;
  color: #8a5a00;
  background: #fff8e6;
  padding: 8px;
  border-radius: 8px;
}
.achat-log {
  flex: 1;
  overflow: auto;
  min-height: 160px;
  padding: 10px;
  background: #f7fafc;
  border-radius: 8px;
}
.achat-empty {
  margin: 0;
  font-size: 13px;
  color: #6b7c8f;
}
.achat-msg {
  margin-bottom: 12px;
}
.achat-msg-label {
  display: block;
  font-size: 11px;
  color: #6b7c8f;
  margin-bottom: 4px;
}
.achat-msg-body {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.55;
}
.achat-msg[data-role='user'] .achat-msg-body {
  color: #1a2b3c;
}
.achat-msg[data-role='assistant'] .achat-msg-body {
  color: #0f3d7a;
}
.achat-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.achat-input {
  width: 100%;
  resize: vertical;
  border: 1px solid #d4e2f4;
  border-radius: 8px;
  padding: 8px 10px;
  font: inherit;
}
.achat-submit {
  align-self: flex-end;
  padding: 8px 16px;
  border: none;
  border-radius: 8px;
  background: #006be6;
  color: #fff;
  cursor: pointer;
}
.achat-submit:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.achat-presets {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.achat-preset-label {
  font-size: 12px;
  color: #6b7c8f;
}
.achat-chip {
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 999px;
  border: 1px solid #d4e2f4;
  background: #f4f9ff;
  cursor: pointer;
}
.achat-chip:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.achat-error {
  margin: 0;
  font-size: 12px;
  color: #b42318;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
</style>
