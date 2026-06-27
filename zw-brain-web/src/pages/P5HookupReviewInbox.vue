<script setup lang="ts">
import { computed, ref } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import { shellNavLabelByKey } from '@/config/productShellNav';
import { useProvider, useSnapshot } from '@/composables/useSnapshot';
import { deriveHookupReviews } from '@/lib/providerProjection';
import { formatTodoStatus, todoStatusTone } from '@/lib/statusLabels';
import { shortId } from '@/lib/userLanguage';
import { invokeActionStub, pushToast } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';
import { canApproveHookup } from '@/lib/requestFlowRoles';

const providerShellTitle = shellNavLabelByKey('provider');
const provider = useProvider();
const { source } = useSnapshot();
const role = getProductRole();
const canApprove = computed(() => canApproveHookup(role.value));

const items = computed(() => deriveHookupReviews(provider.value as Record<string, unknown>));

// D57⑨/R10 去盲批：行内展开被审登记信息（资源形态/所属目录/提供方/挂接位置/描述/共享类型/字段数）。
const expandedId = ref('');
function toggleDetail(id: string) {
  expandedId.value = expandedId.value === id ? '' : id;
}

// 驳回（退回整改）带理由：先点「驳回」展开理由框，填写后确认提交。
const rejectingId = ref('');
const rejectReason = ref('');
function startReject(id: string) {
  rejectingId.value = id;
  rejectReason.value = '';
}
function cancelReject() {
  rejectingId.value = '';
  rejectReason.value = '';
}

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
      detail: '挂接审核由部门管理员办理；部门操作员可先在资源挂接向导完成挂接提交。',
    });
    return;
  }
  await invokeActionStub({
    skillId: 'resource.asset.review',
    payload: { resource_code: resourceCode, decision: 'approve' },
    successTitle: '挂接已通过',
  });
}

async function confirmReject(resourceCode: string) {
  if (!rejectReason.value.trim()) {
    pushToast({ kind: 'warn', title: '请填写驳回理由', detail: '驳回会把资源退回提交方整改，需要说明依据。' });
    return;
  }
  await invokeActionStub({
    skillId: 'resource.asset.review',
    payload: { resource_code: resourceCode, decision: 'return_for_fix', reason: rejectReason.value.trim() },
    successTitle: '已驳回，资源退回提交方整改',
  });
  cancelReject();
}
</script>

<template>
  <main class="focus-page">
    <nav class="crumbs"><a href="#/provider">← {{ providerShellTitle }}</a></nav>
    <section class="panel">
      <PageFocusHeader
        title="挂接审核收件箱"
        :meta="headerMeta"
        :links="[{ label: '反向编目审核', href: '#/provider/inbox/field-decision' }]"
      />

      <table v-if="source === 'live' && items.length" class="focus-table">
        <thead>
          <tr><th>编号</th><th>关联资源</th><th>所属目录</th><th>状态</th><th>操作</th></tr>
        </thead>
        <tbody>
          <template v-for="it in items" :key="it.id">
            <tr data-testid="hookup-review-row">
              <td><code>{{ shortId(it.id) }}</code></td>
              <td>{{ it.title }}</td>
              <td>{{ it.catalog }}</td>
              <td><span class="status-pill" :class="todoStatusTone(it.status)">{{ formatTodoStatus(it.status) }}</span></td>
              <td class="row-actions">
                <button
                  v-if="it.detail"
                  type="button"
                  class="row-link-btn"
                  data-testid="hookup-detail-toggle"
                  @click="toggleDetail(it.id)"
                >{{ expandedId === it.id ? '收起详情' : '查看详情' }}</button>
                <template v-if="canApprove">
                  <button type="button" class="row-link-btn" data-testid="hookup-approve-btn" @click="approve(it.id)">通过挂接</button>
                  <button type="button" class="row-link-btn row-link-btn--danger" data-testid="hookup-reject-btn" @click="startReject(it.id)">驳回</button>
                </template>
              </td>
            </tr>
            <tr v-if="expandedId === it.id && it.detail" class="detail-row" data-testid="hookup-detail-panel">
              <td colspan="5">
                <dl class="hookup-detail">
                  <div><dt>资源形态</dt><dd>{{ it.detail.kindLabel || '—' }}</dd></div>
                  <div><dt>提供方</dt><dd>{{ it.detail.owner || '—' }}</dd></div>
                  <div><dt>挂接位置</dt><dd><code>{{ it.detail.sourceRef || '—' }}</code></dd></div>
                  <div><dt>共享类型</dt><dd>{{ it.detail.shareTypeLabel || '未登记' }}</dd></div>
                  <div><dt>登记字段</dt><dd>{{ it.detail.fieldCount ? `${it.detail.fieldCount} 个字段` : '未登记' }}</dd></div>
                  <div class="hookup-detail-desc"><dt>资源描述</dt><dd>{{ it.detail.desc || '未登记' }}</dd></div>
                </dl>
              </td>
            </tr>
            <tr v-if="rejectingId === it.id" class="detail-row" data-testid="hookup-reject-panel">
              <td colspan="5">
                <div class="reject-box">
                  <label :for="`reject-reason-${it.id}`">驳回理由（退回提交方整改）</label>
                  <textarea :id="`reject-reason-${it.id}`" v-model="rejectReason" rows="3" placeholder="请说明登记信息需要整改的内容" />
                  <div class="reject-actions">
                    <button type="button" class="gov-btn gov-btn-primary" data-testid="hookup-reject-confirm-btn" @click="confirmReject(it.id)">确认驳回</button>
                    <button type="button" class="gov-btn" @click="cancelReject">取消</button>
                  </div>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
      <p v-else-if="source === 'live'" class="focus-empty">暂无挂接审核待办。</p>
      <p v-else class="focus-empty">等待数据装载……</p>
    </section>
  </main>
</template>

<style scoped>
.crumbs { max-width: var(--content-max-width, 1200px); margin: 0 auto 8px; font-size: 14px; }
.crumbs a { color: var(--b-primary, #006be6); text-decoration: none; font-weight: 600; }
.row-actions { display: flex; gap: 10px; align-items: center; }
.row-link-btn { background: none; border: 0; padding: 0; color: var(--b-primary, #006be6); cursor: pointer; font-size: 13px; text-decoration: underline; }
.row-link-btn--danger { color: #b42318; }
.detail-row td { background: var(--b-bg-subtle, #f6faff); }
.hookup-detail { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 8px 24px; margin: 4px 0; }
.hookup-detail div { display: flex; gap: 8px; min-width: 0; }
.hookup-detail dt { flex-shrink: 0; color: var(--b-muted, #5c6370); font-size: 13px; }
.hookup-detail dd { margin: 0; font-size: 13px; word-break: break-all; }
.hookup-detail-desc { grid-column: 1 / -1; }
.reject-box { display: grid; gap: 8px; max-width: 640px; padding: 4px 0; }
.reject-box label { font-size: 13px; color: var(--b-muted, #5c6370); }
.reject-box textarea { width: 100%; padding: 8px 10px; border: 1px solid var(--b-border, #d4e2f4); border-radius: 6px; font-size: 13px; }
.reject-actions { display: flex; gap: 10px; }
.gov-btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid var(--b-border, #d4e2f4); background: #fff; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; border-color: transparent; }
</style>
