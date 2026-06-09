<script setup lang="ts">
import { computed } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import { useDeliveryTasks, useSnapshot } from '@/composables/useSnapshot';
import { invokeActionStub, pushToast } from '@/composables/useActionStub';
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
      // F3 + F4：交付资源类型（table/file/api），驱动操作按钮分流（API=查看授权、file=下载、对账回执非API）。
      resourceKind: String(it.resourceKind ?? ''),
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
// F4 文件资源下载：登记受控下载请求 + 落下载日志（文件名/大小/时间/领取方，对齐旧
// resource_file_download_log）。zw-brain 仅持有文件元数据；文件字节由源存储交付——与 F6
// 库表交换同属外部数据治理底座边界（架构 §3.4）。本期诚实：仅当源存储返回真实可直达地址
// （http/https）才跳转下载，否则如实告知「经源存储交付、对接中」，不把内部受控锚伪造成直链。
async function downloadFile(id: string, name: string) {
  const res = await invokeActionStub({
    skillId: 'delivery.file.download',
    payload: { task_id: id, file_name: name },
    successTitle: '已登记文件下载请求',
  });
  if (!res.ok) return;
  const root = (res.data ?? {}) as Record<string, unknown>;
  const inner = (root.result ?? root) as Record<string, unknown>;
  const link = String(inner.file_link ?? '');
  if (/^https?:\/\//i.test(link)) {
    window.open(link, '_blank', 'noopener');
    return;
  }
  pushToast({
    kind: 'info',
    title: '下载请求已登记',
    detail: '已记录受控下载日志（文件名 / 大小 / 时间 / 领取方）。文件内容由源存储交付，平台正在对接，完成后即可直接下载。',
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
                <!-- F3（6.5#9）：API 交付的凭据语义是「查看授权」（网关 appkey/secret），
                     库表/文件交付仍是「领凭据」。 -->
                <button type="button" class="gov-btn gov-btn-secondary" @click="openCredential(t.requestId)">
                  {{ t.resourceKind === 'api' ? '查看授权' : '领凭据' }}
                </button>
                <!-- F4：文件类资源显「下载」（受控下载请求 + 下载日志）。 -->
                <button
                  v-if="t.resourceKind === 'file'"
                  type="button"
                  class="gov-btn gov-btn-primary"
                  @click="downloadFile(t.id, t.name)"
                >
                  下载
                </button>
                <!-- 「对账回执」= 库表受控交换的对账语义，仅库表交付渲染（业务方 2026-06-09 确认）：
                     API 是接口授权（走「查看授权」）、文件是直接下载（走「下载」），二者均无对账回执概念。 -->
                <button
                  v-if="t.resourceKind === 'table'"
                  type="button"
                  class="gov-btn gov-btn-primary"
                  @click="reconcile(t.id)"
                >
                  对账回执
                </button>
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
