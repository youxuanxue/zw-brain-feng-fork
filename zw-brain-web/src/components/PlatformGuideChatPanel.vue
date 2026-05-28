<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { usePlatformGuideChat } from '@/composables/usePlatformGuideChat';

const PRESETS = [
  '我的角色权限范围是什么？',
  '申请数据资源需要哪些字段？',
  'Docker 如何启用平台问答？',
] as const;

const open = ref(false);
const draft = ref('');
const { messages, loading, error, runtimeEnabled, probeRuntime, ask, clear } = usePlatformGuideChat();

function toggle() {
  open.value = !open.value;
  if (!open.value) {
    draft.value = '';
    clear();
  }
}

async function submit() {
  const q = draft.value.trim();
  if (!q) return;
  draft.value = '';
  await ask(q);
}

function applyPreset(text: string) {
  draft.value = text;
  void ask(text);
}

onMounted(() => {
  void probeRuntime();
});
</script>

<template>
  <div class="platform-guide" :class="{ 'is-open': open }">
    <button
      type="button"
      class="guide-trigger"
      :title="open ? '收起平台指南' : '打开平台指南问答'"
      @click="toggle"
    >
      <span aria-hidden="true">{{ open ? '×' : '?' }}</span>
      <span class="guide-trigger-text">平台指南</span>
    </button>

    <aside v-if="open" class="guide-drawer" role="dialog" aria-label="平台指南问答">
      <header class="guide-head">
        <strong>平台指南</strong>
        <p class="guide-hint">基于项目文档回答部署、权限与使用问题；答案以仓库 Markdown 为准。</p>
        <p v-if="runtimeEnabled === false" class="guide-warn">
          AgentRuntime 未启用，问答不可用。请联系平台管理员开启。
        </p>
      </header>

      <div class="guide-log" aria-live="polite">
        <p v-if="!messages.length" class="guide-empty">输入问题开始对话，或点下方快捷问题。</p>
        <article
          v-for="(msg, idx) in messages"
          :key="idx"
          class="guide-msg"
          :data-role="msg.role"
        >
          <span class="guide-msg-label">{{ msg.role === 'user' ? '我' : '指南' }}</span>
          <pre class="guide-msg-body">{{ msg.text }}</pre>
        </article>
      </div>

      <form class="guide-form" @submit.prevent="submit">
        <label class="sr-only" for="guide-input">平台问题</label>
        <textarea
          id="guide-input"
          v-model="draft"
          class="guide-input"
          rows="3"
          placeholder="例如：REST 默认端口？如何配置 IAF？"
          :disabled="loading"
        />
        <button type="submit" class="guide-submit" :disabled="loading || runtimeEnabled === false">
          {{ loading ? '思考中…' : '发送' }}
        </button>
      </form>

      <div class="guide-presets">
        <span class="guide-preset-label">快捷：</span>
        <button
          v-for="p in PRESETS"
          :key="p"
          type="button"
          class="guide-chip"
          :disabled="loading"
          @click="applyPreset(p)"
        >{{ p }}</button>
      </div>

      <p v-if="error" class="guide-error">{{ error }}</p>
    </aside>
  </div>
</template>

<style scoped>
.platform-guide {
  position: fixed;
  right: 20px;
  bottom: 20px;
  z-index: 1200;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 10px;
}
.guide-trigger {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 999px;
  border: 1px solid #c5d9f2;
  background: #fff;
  color: #0048a8;
  box-shadow: 0 4px 16px rgba(0, 48, 168, 0.12);
  cursor: pointer;
  font-size: 14px;
}
.guide-drawer {
  width: min(420px, calc(100vw - 32px));
  max-height: min(70vh, 640px);
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px;
  border-radius: 12px;
  border: 1px solid #d4e2f4;
  background: #fff;
  box-shadow: 0 8px 28px rgba(15, 35, 70, 0.18);
}
.guide-head .guide-hint {
  margin: 6px 0 0;
  font-size: 12px;
  color: #5a6b7d;
}
.guide-warn {
  margin: 8px 0 0;
  font-size: 12px;
  color: #8a5a00;
  background: #fff8e6;
  padding: 8px;
  border-radius: 8px;
}
.guide-log {
  flex: 1;
  overflow: auto;
  min-height: 120px;
  max-height: 36vh;
  padding: 8px;
  background: #f7fafc;
  border-radius: 8px;
}
.guide-empty {
  margin: 0;
  font-size: 13px;
  color: #6b7c8f;
}
.guide-msg {
  margin-bottom: 10px;
}
.guide-msg-label {
  display: block;
  font-size: 11px;
  color: #6b7c8f;
  margin-bottom: 4px;
}
.guide-msg-body {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.5;
}
.guide-msg[data-role='user'] .guide-msg-body {
  color: #1a2b3c;
}
.guide-msg[data-role='assistant'] .guide-msg-body {
  color: #0f3d7a;
}
.guide-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.guide-input {
  width: 100%;
  resize: vertical;
  border: 1px solid #d4e2f4;
  border-radius: 8px;
  padding: 8px 10px;
  font: inherit;
}
.guide-submit {
  align-self: flex-end;
  padding: 8px 16px;
  border: none;
  border-radius: 8px;
  background: #006be6;
  color: #fff;
  cursor: pointer;
}
.guide-submit:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.guide-presets {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.guide-preset-label {
  font-size: 12px;
  color: #6b7c8f;
}
.guide-chip {
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 999px;
  border: 1px solid #d4e2f4;
  background: #f4f9ff;
  cursor: pointer;
}
.guide-chip:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.guide-error {
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
