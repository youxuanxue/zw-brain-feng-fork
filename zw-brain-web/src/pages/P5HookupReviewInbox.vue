<script setup lang="ts">
import { computed } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import { useProvider, useSnapshot } from '@/composables/useSnapshot';
import { deriveHookupReviews } from '@/lib/providerProjection';
import { formatTodoStatus, todoStatusTone } from '@/lib/statusLabels';
import { invokeActionStub, pushToast } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';
import { canApproveHookup } from '@/lib/requestFlowRoles';

const provider = useProvider();
const { source } = useSnapshot();
const role = getProductRole();
const canApprove = computed(() => canApproveHookup(role.value));

const items = computed(() => deriveHookupReviews(provider.value as Record<string, unknown>));

const headerMeta = computed(() => {
  if (source.value !== 'live') return '正在加载……';
  const n = items.value.length;
  if (!n) return '暂无挂接审核待办';
  const derived = items.value.some((i) => i.source === 'derived');
  return derived ? `${n} 条挂接待办（由已挂资源汇总）` : `${n} 条挂接待审`;
});

async function approve(resourceCode: string) {
  if (!canApprove.value) {
    pushToast({
      kind: 'info',
      title: '暂无审核权限',
      detail: '挂接审核由业务运营员办理；部门管理员可先在资源侧完成挂接提交。',
    });
    return;
  }
  await invokeActionStub({
    skillId: 'resource.asset.review',
    payload: { resource_code: resourceCode, decision: 'approve' },
    successTitle: '挂接已通过',
    role: 'ROLE_BUSIAUDIT',
  });
}
</script>

<template>
  <main class="focus-page">
    <section class="panel">
      <PageFocusHeader
        title="挂接审核收件箱"
        :meta="headerMeta"
        :links="[
          { label: '提供方管理', href: '#/provider' },
          { label: '字段裁决', href: '#/provider/inbox/field-decision' },
        ]"
      />

      <p v-if="source === 'live' && items.length && !canApprove" class="role-hint">
        当前岗位为部门管理员；挂接「通过」需切换为业务运营员办理。
      </p>

      <table v-if="source === 'live' && items.length" class="focus-table">
        <thead>
          <tr><th>编号</th><th>关联资源</th><th>事项</th><th>状态</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="it in items" :key="it.id">
            <td><code>{{ it.id }}</code></td>
            <td>{{ it.catalog }}</td>
            <td>{{ it.title }}</td>
            <td><span class="status-pill" :class="todoStatusTone(it.status)">{{ formatTodoStatus(it.status) }}</span></td>
            <td>
              <button type="button" class="row-link-btn" @click="approve(it.id)">通过挂接</button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else-if="source === 'live'" class="focus-empty">暂无挂接审核待办。</p>
      <p v-else class="focus-empty">等待数据装载……</p>
    </section>
  </main>
</template>

<style scoped>
.row-link-btn { background: none; border: 0; color: var(--b-primary, #006be6); cursor: pointer; font-size: 13px; text-decoration: underline; }
.role-hint { font-size: 13px; color: var(--b-muted, #5c6370); margin: 0 0 10px; }
</style>
