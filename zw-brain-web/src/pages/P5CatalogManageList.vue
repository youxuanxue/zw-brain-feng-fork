<script setup lang="ts">
import { computed } from 'vue';
import ProviderManageList from '@/components/ProviderManageList.vue';
import { shellNavLabelByKey } from '@/config/productShellNav';
import type { ProviderAssetRow } from '@/lib/providerProjection';
import { useProvider, useSnapshot } from '@/composables/useSnapshot';
import { invokeActionStub } from '@/composables/useActionStub';
import { providerCatalogRows } from '@/lib/providerProjection';
import { canViewProviderAssets, canAuthorInlineCatalog } from '@/lib/requestFlowRoles';
import { getProductRole } from '@/composables/useProductRole';

// 供数侧「目录管理清单」（T9）：供数人除审批待办外，按生命周期浏览本部门已编目目录全量行。
// 纯 snapshot 投影、只读管理态——不在左导航增项（守左导航场景页 ≤10 约束），由「供数据」概览卡点入。
// 视图门=供数三岗位只读浏览（业务方 2026-06-09：操作员=编制者也需看本部门清单跟踪状态）；
// C：草稿行加行内「继续编辑」「提交审核」（编制岗位 canAuthorInlineCatalog 才渲染）。表壳复用 ProviderManageList。
const providerShellTitle = shellNavLabelByKey('provider');
const provider = useProvider();
const { source } = useSnapshot();
const role = getProductRole();
const canView = computed(() => canViewProviderAssets(role.value));
// 行内动作门 = 在线编制岗位（部门操作员/管理员，与向导 + 后端 submit_review 角色门一致）。
const canAct = computed(() => canAuthorInlineCatalog(role.value));
const rows = computed(() => providerCatalogRows(provider.value as Record<string, unknown>));
const meta = computed(() => {
  if (source.value !== 'live') return '正在加载……';
  const n = rows.value.length;
  return n ? `本部门目录 ${n} 项（按生命周期浏览全部）` : '本部门暂无已编目目录';
});

// C：草稿行「提交审核」→ catalog.entry.submit_review（actionId=内部 catalog_code）。
// 写后 refreshSnapshotAfter 让清单生命周期态即时翻新（草稿→审核中、行内动作随之收起）。
async function onRowAction({ actionId }: { actionId: string; row: ProviderAssetRow }) {
  await invokeActionStub({
    skillId: 'catalog.entry.submit_review',
    payload: { catalog_code: actionId },
    successTitle: '已提交部门审核',
    role: role.value,
    refreshSnapshotAfter: true,
  });
}
</script>

<template>
  <ProviderManageList
    title="目录管理清单"
    :meta="meta"
    :back-link="{ label: providerShellTitle, href: '#/provider' }"
    :links="[
      { label: '资源管理清单', href: '#/provider/resources' },
      { label: '在线编制目录', href: '#/provider/wizard/inline-catalog' },
    ]"
    :columns="[
      { label: '目录名称', key: 'name' },
      { label: '目录编号', key: 'code', mono: true },
      { label: '提供方', key: 'owner' },
      { label: '生命周期', key: 'status', pill: true },
    ]"
    :rows="rows"
    :loaded="source === 'live'"
    :can-view="canView"
    :can-act="canAct"
    empty-text="本部门暂无已编目目录。"
    empty-filtered-text="暂无匹配的目录数据"
    deny-text="当前岗位无目录管理视图权限。"
    testid="provider-catalog-list"
    @row-action="onRowAction"
  />
</template>
