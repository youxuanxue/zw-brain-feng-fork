<script setup lang="ts">
import { computed } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import { useDeliveryTasks, useSnapshot } from '@/composables/useSnapshot';
import { invokeActionStub } from '@/composables/useActionStub';
import { formatTodoStatus, todoStatusTone } from '@/lib/statusLabels';
import { deriveRecordName, formatChannel, formatTime, shortId } from '@/lib/userLanguage';

const tasks = useDeliveryTasks();
const { source } = useSnapshot();
const items = computed(() =>
  tasks.value.map((t) => {
    const it = t as Record<string, unknown>;
    const status = String(it.status ?? '');
    const id = String(it.id ?? '');
    return {
      id,
      idShort: shortId(id),
      // 名缺失 / 名本身是裸 hex → 派生「交付任务 …末6位」，不裸出 32 位 hex 主文本。
      name: deriveRecordName(it.name, id, '交付任务'),
      requestId: String(it.requestId ?? ''),
      channel: formatChannel(it.channel),
      status,
      statusLabel: formatTodoStatus(status),
      updatedAt: formatTime(it.updatedAt),
    };
  })
);

const headerMeta = computed(() => {
  if (source.value !== 'live') return '正在加载……';
  return items.value.length ? `${items.value.length} 条 · 领凭据、对账回执在此办理` : '暂无任务 · 审批通过后会出现在此';
});

async function openCredential(reqId: string) {
  if (reqId) window.location.hash = `#/delivery-exchange/credential/${reqId}`;
}
async function reconcile(id: string) {
  await invokeActionStub({
    skillId: 'delivery.reconcile_receipt',
    payload: { task_id: id },
    successTitle: '已触发对账',
  });
}
</script>

<template>
  <main class="focus-page">
    <section class="panel">
      <PageFocusHeader
        title="交付任务"
        :meta="headerMeta"
        :links="[
          { label: '申请进度', href: '#/request-flow' },
          { label: '提异议', href: '#/request-flow/objection/new' },
          { label: '审计回放', href: '#/compliance-ops' },
        ]"
      />

      <p class="page-intro">
        本页办理审批通过后的数据交付：「领凭据」获取访问数据的授权密钥，「对账回执」核对本次受控交付的明细与结果。
      </p>

      <table v-if="source === 'live' && items.length" class="focus-table">
        <thead>
          <tr>
            <th>编号</th>
            <th>名称</th>
            <th>渠道</th>
            <th>状态</th>
            <th>更新</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="t in items" :key="t.id">
            <td><a :href="`#/delivery-exchange/task/${t.id}`"><code>{{ t.idShort }}</code></a></td>
            <td>{{ t.name }}</td>
            <td>{{ t.channel }}</td>
            <td><span class="status-pill" :class="todoStatusTone(t.status)">{{ t.statusLabel }}</span></td>
            <td>{{ t.updatedAt }}</td>
            <td class="table-actions">
              <div class="table-actions-inner">
                <button type="button" class="gov-btn gov-btn-secondary" @click="openCredential(t.requestId)">领凭据</button>
                <button type="button" class="gov-btn gov-btn-primary" @click="reconcile(t.id)">对账回执</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else-if="source === 'live'" class="focus-empty">暂无交付任务。</p>
      <p v-else class="focus-empty">等待数据装载……</p>
    </section>
  </main>
</template>

<style scoped>
.page-intro { margin: 8px 0 14px; font-size: 13px; line-height: 1.7; color: var(--b-muted, #5c6370); }
.gov-btn { padding: 4px 10px; border-radius: 6px; font-size: 12px; cursor: pointer; border: 1px solid transparent; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-secondary { background: #fff; border-color: var(--b-border, #d4e2f4); }
</style>
