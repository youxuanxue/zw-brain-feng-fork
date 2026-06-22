<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import { useSnapshot } from '@/composables/useSnapshot';
import { authFetch } from '@/composables/useAuth';
import { invokeActionStub } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';
import { canReviewCatalogDept, canReviewCatalogPlatform } from '@/lib/requestFlowRoles';
import { apiUrl } from '@/composables/useApiBase';
import { displayRecordName } from '@/lib/userLanguage';

const { source } = useSnapshot();
const role = getProductRole();

const canDeptReview = computed(() => canReviewCatalogDept(role.value));
const canPlatformReview = computed(() => canReviewCatalogPlatform(role.value));

const reviewStage = computed<'dept' | 'platform' | 'none'>(() => {
  if (canDeptReview.value) return 'dept';
  if (canPlatformReview.value) return 'platform';
  return 'none';
});

const targetLifecycleStatus = computed(() => {
  if (reviewStage.value === 'dept') return 'pending_review';
  if (reviewStage.value === 'platform') return 'pending_platform_review';
  return '';
});

const stageLabel = computed(() => {
  if (reviewStage.value === 'dept') return '部门审';
  if (reviewStage.value === 'platform') return '平台审';
  return '审核';
});

const nextLifecycleHint = computed(() => {
  if (reviewStage.value === 'dept') return '通过后流转至平台审';
  if (reviewStage.value === 'platform') return '通过后进入发布队列';
  return '';
});

interface CatalogReviewRow {
  catalog_code: string;
  /** 展示码：业务码（数据资源目录代码 DRC-…）优先，缺则回落内部码。 */
  display_code: string;
  title: string;
  /** 责任单位：机构中文名优先（后端 ReferenceService 补名），缺则回落 org id 诚实展示。 */
  owner: string;
  /** 区划：中文名优先，缺则回落区划码。 */
  region: string;
  lifecycle_label: string;
  updated_at: string;
}

const items = ref<CatalogReviewRow[]>([]);
const loading = ref(false);
const errorMsg = ref('');

async function loadInbox(): Promise<void> {
  if (!targetLifecycleStatus.value) {
    items.value = [];
    return;
  }
  loading.value = true;
  errorMsg.value = '';
  try {
    const resp = await authFetch(apiUrl('/api/skills/catalog.entry.query'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      // 0611 断点 A 同株（#251 复审 R004）：全量（去 limit:20 截断）+ 按提交/更新时间倒序——
      // 缺省 catalog_code 升序时新提交 j2-* 目录排存量数字码之后、配合截断永不可见，
      // 且收件箱条数与工作台待审计数（同口径全量 count）自相矛盾。行多时容器内滚动。
      body: JSON.stringify({
        role: role.value,
        lifecycle_status: targetLifecycleStatus.value,
        order: 'updated_desc',
      }),
    });
    if (!resp.ok) {
      items.value = [];
      errorMsg.value = '暂时无法加载待审目录，请稍后再试。';
      return;
    }
    const body = (await resp.json()) as { items?: Array<Record<string, unknown>> };
    items.value = (body.items ?? [])
      .map((it) => {
        const summary = (it.summary_json ?? {}) as Record<string, unknown>;
        return {
          catalog_code: String(it.catalog_code ?? ''),
          display_code: String(summary.data_catalog_code ?? '') || String(it.catalog_code ?? ''),
          // 名缺失 / 名==catalog_code / 名是裸编码 → 「未命名目录（编码 …）」，不把目录码当名直出（R12）。
          title: displayRecordName(it.title, it.catalog_code, '目录'),
          owner: String(it.owner_org_name ?? '') || String(it.owner_org_id ?? ''),
          region: String(it.region_name ?? '') || String(it.region_code ?? ''),
          // 展示态取后端下发的中文 lifecycle_label（前端零词表，R12），不直出机器 slug。
          lifecycle_label: String(it.lifecycle_label ?? ''),
          updated_at: String(it.updated_at ?? it.updatedAt ?? ''),
        };
      })
      .filter((it) => it.catalog_code);
  } finally {
    loading.value = false;
  }
}

watch(source, (live) => {
  if (live === 'live') void loadInbox();
}, { immediate: true });

watch(role, () => {
  void loadInbox();
});

// 驳回须带理由——展开行内理由框，无理由不可提交（按钮禁用）。
// 通过无须理由，直接处置。后端同样硬拦无理由的驳回（前端只是第一道）。
// 注意：本页「驳回」= 目录终态枪毙（后端落 rejected，无回 draft 路径），
// 不是退回整改；理由仅作终止凭据，文案不得承诺「整改/重提」（诚实化）。
const rejectingCode = ref('');
const rejectReason = ref('');

function startReject(catalogCode: string) {
  rejectingCode.value = catalogCode;
  rejectReason.value = '';
}

function cancelReject() {
  rejectingCode.value = '';
  rejectReason.value = '';
}

async function approve(catalogCode: string) {
  const result = await invokeActionStub({
    skillId: 'catalog.entry.review',
    payload: { catalog_code: catalogCode, decision: 'approve' },
    successTitle: '已通过审核',
    refreshSnapshotAfter: true,
  });
  if (!result.ok) return;
  await loadInbox();
}

async function confirmReject() {
  const code = rejectingCode.value;
  const reason = rejectReason.value.trim();
  if (!code || !reason) return; // 无理由不提交（按钮已禁用，此处兜底）
  const result = await invokeActionStub({
    skillId: 'catalog.entry.review',
    payload: { catalog_code: code, decision: 'reject', reason },
    successTitle: '已驳回',
    refreshSnapshotAfter: true,
  });
  if (!result.ok) return;
  cancelReject();
  await loadInbox();
}

const headerMeta = computed(() => {
  if (reviewStage.value === 'none') return '请切换为部门管理员或业务运营员办理目录审核';
  if (loading.value) return '正在加载……';
  const n = items.value.length;
  if (!n) return `暂无${stageLabel.value}待办`;
  return `${n} 条${stageLabel.value}待办 · ${nextLifecycleHint.value}`;
});
</script>

<template>
  <main class="focus-page">
    <section class="panel">
      <PageFocusHeader
        title="目录审核收件箱"
        :meta="headerMeta"
        :links="[
          { label: '提供方管理', href: '#/provider' },
          { label: '在线编制', href: '#/provider/wizard/inline-catalog' },
        ]"
      />

      <p v-if="reviewStage === 'none'" class="role-hint">
        目录审核由部门管理员办理部门审、业务运营员办理平台审；请切换岗位后再办理。
      </p>

      <div v-else>
        <p v-if="errorMsg" class="error-msg">{{ errorMsg }}</p>

        <div v-if="items.length" class="inbox-scroll">
        <table class="focus-table">
          <thead>
            <tr>
              <th>目录编号</th>
              <th>名称</th>
              <th>责任单位</th>
              <th>区划</th>
              <th>当前状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="it in items" :key="it.catalog_code">
            <tr>
              <!-- T10（6.5#8）：编号/名称跳目录详情，审核人看全貌再判通过/驳回（复用 P2 目录详情页）。 -->
              <td>
                <a
                  class="catalog-link"
                  :href="`#/provider/catalog/${encodeURIComponent(it.catalog_code)}`"
                  data-testid="catalog-review-detail-link"
                ><code>{{ it.display_code }}</code></a>
              </td>
              <td>
                <a class="catalog-link" :href="`#/provider/catalog/${encodeURIComponent(it.catalog_code)}`">{{ it.title }}</a>
              </td>
              <td>{{ it.owner || '—' }}</td>
              <td>{{ it.region || '—' }}</td>
              <td><span class="status-pill">{{ it.lifecycle_label }}</span></td>
              <td>
                <button
                  type="button"
                  class="row-link-btn approve"
                  data-testid="catalog-review-approve-btn"
                  @click="approve(it.catalog_code)"
                >
                  通过
                </button>
                <button
                  type="button"
                  class="row-link-btn reject"
                  data-testid="catalog-review-reject-btn"
                  @click="startReject(it.catalog_code)"
                >
                  驳回
                </button>
              </td>
            </tr>
            <!-- 驳回理由行（无理由不可提交）——展开在被驳回行下方；驳回为终态。 -->
            <tr v-if="rejectingCode === it.catalog_code" class="reject-row">
              <td :colspan="6">
                <div class="reject-box">
                  <label class="reject-label">驳回理由（目录终止受理，不可重提；必填）</label>
                  <textarea
                    v-model="rejectReason"
                    class="reject-input"
                    rows="2"
                    placeholder="例如：信息项缺少主键标识，目录口径不成立，予以终止受理。"
                    data-testid="catalog-review-reject-reason"
                  ></textarea>
                  <div class="reject-actions">
                    <button
                      type="button"
                      class="gov-btn gov-btn-danger"
                      :disabled="!rejectReason.trim()"
                      data-testid="catalog-review-reject-confirm-btn"
                      @click="confirmReject"
                    >确认驳回</button>
                    <button type="button" class="gov-btn gov-btn-plain" @click="cancelReject">取消</button>
                  </div>
                </div>
              </td>
            </tr>
            </template>
          </tbody>
        </table>
        </div>
        <p v-else-if="!loading" class="focus-empty">暂无{{ stageLabel }}待办。</p>
      </div>
    </section>
  </main>
</template>

<style scoped>
/* 收件箱全量呈现（同 0611 断点 A：去 limit 截断）；行多时容器内滚动，不无限撑长页面。 */
.inbox-scroll { max-height: 560px; overflow-y: auto; }
.row-link-btn { background: none; border: 0; cursor: pointer; font-size: 13px; text-decoration: underline; margin-right: 12px; padding: 0; }
.catalog-link { color: var(--b-primary, #006be6); text-decoration: none; }
.catalog-link:hover { text-decoration: underline; }
.catalog-link code { color: inherit; }
.row-link-btn.approve { color: var(--b-primary, #006be6); }
.row-link-btn.reject { color: #c0392b; }
.role-hint { font-size: 13px; color: var(--b-muted, #5c6370); margin: 0 0 12px; line-height: 1.5; }
.status-pill { display: inline-block; padding: 2px 8px; border-radius: 10px; background: #eef4fb; color: var(--b-primary, #006be6); font-size: 12px; }
.error-msg { font-size: 13px; color: #c0392b; margin: 0 0 10px; }
.reject-row td { background: #fdf6f4; border-top: 0; }
.reject-box { display: flex; flex-direction: column; gap: 6px; padding: 4px 2px 8px; }
.reject-label { font-size: 12px; color: var(--b-muted, #5c6370); }
.reject-input { width: 100%; max-width: 640px; padding: 6px 10px; border: 1px solid var(--b-border, #d4e2f4); border-radius: 6px; font-size: 13px; resize: vertical; font-family: inherit; box-sizing: border-box; }
.reject-actions { display: flex; gap: 10px; }
.gov-btn { padding: 5px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid var(--b-border, #d4e2f4); background: #fff; }
.gov-btn-danger { background: #c0392b; color: #fff; border-color: transparent; }
.gov-btn-danger:disabled { opacity: 0.5; cursor: not-allowed; }
.gov-btn-plain { background: #fff; }
</style>
