<script setup lang="ts">
import { computed } from 'vue';
import ProviderManageList from '@/components/ProviderManageList.vue';
import { useProvider, useSnapshot } from '@/composables/useSnapshot';
import { providerCatalogRows } from '@/lib/providerProjection';
import { canViewProviderAssets } from '@/lib/requestFlowRoles';
import { getProductRole } from '@/composables/useProductRole';

// 供数侧「目录管理清单」（T9）：供数人除审批待办外，按生命周期浏览本部门已编目目录全量行。
// 纯 snapshot 投影、只读管理态——不在左导航增项（守左导航场景页 ≤10 约束），由「供数据」概览卡点入。
// 视图门=供数三岗位只读浏览（业务方 2026-06-09：操作员=编制者也需看本部门清单跟踪状态）；
// 清单无行内管理动作，故比发布岗更宽。表壳复用 ProviderManageList。
const provider = useProvider();
const { source } = useSnapshot();
const role = getProductRole();
const canView = computed(() => canViewProviderAssets(role.value));
const rows = computed(() => providerCatalogRows(provider.value as Record<string, unknown>));
const meta = computed(() => {
  if (source.value !== 'live') return '正在加载……';
  const n = rows.value.length;
  return n ? `本部门目录 ${n} 项（按生命周期浏览全部）` : '本部门暂无已编目目录';
});
</script>

<template>
  <ProviderManageList
    title="目录管理清单"
    :meta="meta"
    :links="[
      { label: '提供方管理', href: '#/provider' },
      { label: '资源管理清单', href: '#/provider/resources' },
      { label: '在线编制目录', href: '#/provider/wizard/inline-catalog' },
    ]"
    :columns="[
      { label: '目录名称', key: 'name' },
      { label: '目录代码', key: 'code', mono: true },
      { label: '提供方', key: 'owner' },
      { label: '生命周期', key: 'status', pill: true },
    ]"
    :rows="rows"
    :loaded="source === 'live'"
    :can-view="canView"
    empty-text="本部门暂无已编目目录。"
    deny-text="当前岗位无目录管理视图权限。"
    testid="provider-catalog-list"
  />
</template>
