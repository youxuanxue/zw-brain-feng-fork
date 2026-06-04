<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import { useSnapshot, useWebUiConfig } from '@/composables/useSnapshot';
import { authFetch } from '@/composables/useAuth';
import { invokeActionStub } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';
import { canCompileNationalExtElem } from '@/lib/requestFlowRoles';
import { apiUrl } from '@/composables/useApiBase';

// 编制能力 slug（单一调用入口；亦是段52 webui 渲染消费锚）。
const COMPILE_SKILL = 'catalog.national_ext_elem.compile';

const { source } = useSnapshot();
const webui = useWebUiConfig();
const role = getProductRole();

const canCompile = computed(() => canCompileNationalExtElem(role.value));

// 国家通道运行三态（后端 snapshot.webui.nationalChannel 单一事实源）。
const nationalChannel = computed(
  () => (webui.value.nationalChannel as Record<string, unknown> | undefined) ?? {},
);
const channelEnabled = computed(() => nationalChannel.value.enabled === true);
const channelProvisioned = computed(() => nationalChannel.value.provisioned === true);
const channelNotice = computed(() => String(nationalChannel.value.notice ?? '国家通道待配置接入信息'));

// 编制态中文标签（R12：用户可见不暴露英文枚举码）。
const STATUS_LABEL: Record<string, string> = {
  draft: '草稿',
  pending_business_review: '待业务部门审核',
  pending_supervisor_review: '待主管部门审核',
  published: '已发布',
  revision_draft: '变更草稿',
  pending_business_review_revision: '变更待业务部门审核',
  pending_supervisor_review_revision: '变更待主管部门审核',
  pending_revoke_review: '撤销待审核',
  revoked: '已撤销',
};
function statusLabel(code: string): string {
  return STATUS_LABEL[code] ?? '处理中';
}

interface CompileTask {
  task_code: string;
  title: string;
  compile_status: string;
}

const items = ref<CompileTask[]>([]);
const loading = ref(false);
const errorMsg = ref('');
const newCode = ref('');
const newTitle = ref('');

async function loadTasks(): Promise<void> {
  if (!canCompile.value || !channelEnabled.value) {
    items.value = [];
    return;
  }
  loading.value = true;
  errorMsg.value = '';
  try {
    const resp = await authFetch(apiUrl(`/api/skills/${COMPILE_SKILL}`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ role: role.value, confirmed: true, action: 'list' }),
    });
    if (!resp.ok) {
      items.value = [];
      errorMsg.value = '编制任务暂时无法加载，请稍后重试。';
      return;
    }
    const body = (await resp.json()) as { items?: Array<Record<string, unknown>> };
    items.value = (body.items ?? [])
      .map((it) => ({
        task_code: String(it.task_code ?? ''),
        title: String(it.title ?? it.task_code ?? '—'),
        compile_status: String(it.compile_status ?? 'draft'),
      }))
      .filter((it) => it.task_code);
  } finally {
    loading.value = false;
  }
}

watch(source, (live) => {
  if (live === 'live') void loadTasks();
}, { immediate: true });
watch([role, channelEnabled], () => void loadTasks());

async function createDraft(): Promise<void> {
  if (!newCode.value.trim()) return;
  const result = await invokeActionStub({
    skillId: COMPILE_SKILL,
    payload: { action: 'create', task_code: newCode.value.trim(), title: newTitle.value.trim() || newCode.value.trim() },
    successTitle: '已创建编制草稿',
  });
  if (!result.ok) return;
  newCode.value = '';
  newTitle.value = '';
  await loadTasks();
}

async function submitTask(code: string): Promise<void> {
  const result = await invokeActionStub({ skillId: COMPILE_SKILL, payload: { action: 'submit', task_code: code }, successTitle: '已提交送审' });
  if (result.ok) await loadTasks();
}

async function reviewTask(code: string): Promise<void> {
  const result = await invokeActionStub({ skillId: COMPILE_SKILL, payload: { action: 'review', task_code: code, approve: true }, successTitle: '已通过审核' });
  if (result.ok) await loadTasks();
}

const headerMeta = computed(() => {
  if (!canCompile.value) return '本岗位无权办理国家扩展要素编制';
  if (!channelEnabled.value) return channelNotice.value;
  if (loading.value) return '正在加载……';
  return `${items.value.length} 项编制任务 · ${channelNotice.value}`;
});
</script>

<template>
  <main class="focus-page">
    <section class="panel">
      <PageFocusHeader
        title="国家扩展要素编制"
        :meta="headerMeta"
        :links="[{ label: '提供方管理', href: '#/provider' }]"
      />

      <p v-if="!canCompile" class="role-hint">
        国家扩展要素编制由「部门管理员（ROLE_ORGAN_MANAGER）」编制、「业务运营员（ROLE_BUSIAUDIT）」主管审核办理。
      </p>

      <p v-else-if="!channelEnabled" class="role-hint">{{ channelNotice }}</p>

      <div v-else>
        <p v-if="!channelProvisioned" class="notice-pending">
          {{ channelNotice }}；当前可草拟与审核编制目录，「发布并同步国家平台」待接入信息配齐后可用。
        </p>

        <div class="new-row">
          <input v-model="newCode" class="ipt" placeholder="编制目录编号（如 C_NAT_001）" data-testid="nat-ext-new-code" />
          <input v-model="newTitle" class="ipt" placeholder="目录名称" data-testid="nat-ext-new-title" />
          <button type="button" class="primary-btn" data-testid="nat-ext-create-btn" @click="createDraft">新建编制草稿</button>
        </div>

        <p v-if="errorMsg" class="error-msg">{{ errorMsg }}</p>

        <table v-if="items.length" class="focus-table">
          <thead>
            <tr><th>目录编号</th><th>名称</th><th>当前状态</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="it in items" :key="it.task_code">
              <td><code>{{ it.task_code }}</code></td>
              <td>{{ it.title }}</td>
              <td><span class="status-pill">{{ statusLabel(it.compile_status) }}</span></td>
              <td>
                <button
                  v-if="it.compile_status === 'draft' || it.compile_status === 'revision_draft'"
                  type="button" class="row-link-btn" data-testid="nat-ext-submit-btn"
                  @click="submitTask(it.task_code)"
                >提交送审</button>
                <button
                  v-else-if="it.compile_status === 'pending_business_review' || it.compile_status === 'pending_business_review_revision'"
                  type="button" class="row-link-btn" data-testid="nat-ext-business-review-btn"
                  @click="reviewTask(it.task_code)"
                >业务部门审核通过</button>
                <button
                  v-else-if="it.compile_status === 'pending_supervisor_review' || it.compile_status === 'pending_supervisor_review_revision'"
                  type="button" class="row-link-btn publish" data-testid="nat-ext-publish-btn"
                  :disabled="!channelProvisioned"
                  :title="channelProvisioned ? '' : channelNotice"
                  @click="reviewTask(it.task_code)"
                >主管审核并发布（同步国家平台）</button>
                <span v-else class="muted">—</span>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else-if="!loading" class="focus-empty">暂无编制任务，可新建编制草稿。</p>
      </div>
    </section>
  </main>
</template>

<style scoped>
.role-hint { font-size: 13px; color: var(--b-muted, #5c6370); margin: 0 0 12px; line-height: 1.5; }
.notice-pending { font-size: 13px; color: #8a6d00; background: #fff7e0; padding: 8px 12px; border-radius: 6px; margin: 0 0 14px; }
.new-row { display: flex; gap: 8px; margin: 0 0 14px; flex-wrap: wrap; }
.ipt { padding: 6px 10px; border: 1px solid var(--b-border, #d0d7de); border-radius: 6px; font-size: 13px; min-width: 200px; }
.primary-btn { padding: 6px 14px; border: 0; border-radius: 6px; background: var(--b-primary, #006be6); color: #fff; cursor: pointer; font-size: 13px; }
.row-link-btn { background: none; border: 0; cursor: pointer; font-size: 13px; text-decoration: underline; margin-right: 12px; padding: 0; color: var(--b-primary, #006be6); }
.row-link-btn.publish:disabled { color: var(--b-muted, #9aa0a6); cursor: not-allowed; text-decoration: none; }
.status-pill { display: inline-block; padding: 2px 8px; border-radius: 10px; background: #eef4fb; color: var(--b-primary, #006be6); font-size: 12px; }
.error-msg { font-size: 13px; color: #c0392b; margin: 0 0 10px; }
.muted { color: var(--b-muted, #9aa0a6); }
</style>
