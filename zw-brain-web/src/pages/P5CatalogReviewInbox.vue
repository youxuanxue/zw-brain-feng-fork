<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import { useSnapshot } from '@/composables/useSnapshot';
import { authFetch } from '@/composables/useAuth';
import { invokeActionStub } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';
import { canReviewCatalogDept, canReviewCatalogPlatform } from '@/lib/requestFlowRoles';
import { apiUrl } from '@/composables/useApiBase';

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
  title: string;
  owner_org_id: string;
  region_code: string;
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
      body: JSON.stringify({
        role: role.value,
        lifecycle_status: targetLifecycleStatus.value,
        limit: 20,
      }),
    });
    if (!resp.ok) {
      items.value = [];
      errorMsg.value = '暂时无法加载待审目录，请稍后再试。';
      return;
    }
    const body = (await resp.json()) as { items?: Array<Record<string, unknown>> };
    items.value = (body.items ?? [])
      .map((it) => ({
        catalog_code: String(it.catalog_code ?? ''),
        title: String(it.title ?? it.catalog_code ?? '—'),
        owner_org_id: String(it.owner_org_id ?? ''),
        region_code: String(it.region_code ?? ''),
        // 展示态取后端下发的中文 lifecycle_label（前端零词表，R12），不直出机器 slug。
        lifecycle_label: String(it.lifecycle_label ?? ''),
        updated_at: String(it.updated_at ?? it.updatedAt ?? ''),
      }))
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

async function decide(catalogCode: string, decision: 'approve' | 'reject') {
  const result = await invokeActionStub({
    skillId: 'catalog.entry.review',
    payload: { catalog_code: catalogCode, decision },
    successTitle: decision === 'approve' ? '已通过审核' : '已驳回',
    refreshSnapshotAfter: true,
  });
  if (!result.ok) return;
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
        当前岗位为「{{ role }}」；目录审核由「部门管理员（ROLE_ORGAN_MANAGER）」办理部门审、
        由「业务运营员（ROLE_BUSIAUDIT）」办理平台审。
      </p>

      <div v-else>
        <p v-if="errorMsg" class="error-msg">{{ errorMsg }}</p>

        <table v-if="items.length" class="focus-table">
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
            <tr v-for="it in items" :key="it.catalog_code">
              <!-- T10（6.5#8）：编号/名称跳目录详情，审核人看全貌再判通过/驳回（复用 P2 目录详情页）。 -->
              <td>
                <a
                  class="catalog-link"
                  :href="`#/discovery/catalog/${encodeURIComponent(it.catalog_code)}`"
                  data-testid="catalog-review-detail-link"
                ><code>{{ it.catalog_code }}</code></a>
              </td>
              <td>
                <a class="catalog-link" :href="`#/discovery/catalog/${encodeURIComponent(it.catalog_code)}`">{{ it.title }}</a>
              </td>
              <td>{{ it.owner_org_id || '—' }}</td>
              <td>{{ it.region_code || '—' }}</td>
              <td><span class="status-pill">{{ it.lifecycle_label }}</span></td>
              <td>
                <button
                  type="button"
                  class="row-link-btn approve"
                  data-testid="catalog-review-approve-btn"
                  @click="decide(it.catalog_code, 'approve')"
                >
                  通过
                </button>
                <button
                  type="button"
                  class="row-link-btn reject"
                  data-testid="catalog-review-reject-btn"
                  @click="decide(it.catalog_code, 'reject')"
                >
                  驳回
                </button>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else-if="!loading" class="focus-empty">暂无{{ stageLabel }}待办。</p>
      </div>
    </section>
  </main>
</template>

<style scoped>
.row-link-btn { background: none; border: 0; cursor: pointer; font-size: 13px; text-decoration: underline; margin-right: 12px; padding: 0; }
.catalog-link { color: var(--b-primary, #006be6); text-decoration: none; }
.catalog-link:hover { text-decoration: underline; }
.catalog-link code { color: inherit; }
.row-link-btn.approve { color: var(--b-primary, #006be6); }
.row-link-btn.reject { color: #c0392b; }
.role-hint { font-size: 13px; color: var(--b-muted, #5c6370); margin: 0 0 12px; line-height: 1.5; }
.status-pill { display: inline-block; padding: 2px 8px; border-radius: 10px; background: #eef4fb; color: var(--b-primary, #006be6); font-size: 12px; }
.error-msg { font-size: 13px; color: #c0392b; margin: 0 0 10px; }
</style>
