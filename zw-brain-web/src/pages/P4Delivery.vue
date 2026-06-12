<script setup lang="ts">
import { computed } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import { useDeliveryTasks, useSnapshot } from '@/composables/useSnapshot';
import { downloadDeliveryFile } from '@/composables/useDeliveryDownload';
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
      // F3 + F4：交付资源类型（table/file/api），驱动操作按钮分流（API=查看授权、文件=下载、库表=交换任务）。
      resourceKind: String(it.resourceKind ?? ''),
    };
  })
);

const headerMeta = computed(() => {
  if (source.value !== 'live') return '正在加载……';
  return items.value.length ? `${items.value.length} 条 · 查看授权、下载、交换任务在此办理` : '暂无任务 · 审批通过后会出现在此';
});

async function openCredential(reqId: string) {
  if (reqId) window.location.hash = `#/delivery-exchange/credential/${reqId}`;
}
function openTask(id: string) {
  if (id) window.location.hash = `#/delivery-exchange/task/${id}`;
}
// F4 文件资源下载：语义与文案单源在 useDeliveryDownload（列表页 / 任务详情页共用），模板直绑。
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
        本页办理审批通过后的数据交付：接口服务「查看授权」、文件资源「下载」；库表数据按「交换任务」送达——在任务中查看送达进度，并核对本次交换的明细与结果。
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
                <!-- 按资源类型分流（0611 业务口径确认单 §B，2026-06-12 方案 B 终裁；
                     old/问题反馈/问题反馈-0611-业务口径确认单.md）：
                     API=「查看授权」（网关 appkey/secret）、文件=「下载」（受控下载请求 + 下载日志）、
                     库表=「交换任务」单一入口（点进任务详情查看送达进度、核对交换结果）；
                     类型推不出时回落「查看授权」（与凭据页通用授权呈现同源）。 -->
                <button
                  v-if="t.resourceKind === 'file'"
                  type="button"
                  class="gov-btn gov-btn-primary"
                  @click="downloadDeliveryFile(t.id, t.name)"
                >
                  下载
                </button>
                <button
                  v-else-if="t.resourceKind === 'table'"
                  type="button"
                  class="gov-btn gov-btn-primary"
                  @click="openTask(t.id)"
                >
                  交换任务
                </button>
                <button v-else type="button" class="gov-btn gov-btn-secondary" @click="openCredential(t.requestId)">
                  查看授权
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
