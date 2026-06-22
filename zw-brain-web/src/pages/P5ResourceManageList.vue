<script setup lang="ts">
import { computed } from 'vue';
import ProviderManageList from '@/components/ProviderManageList.vue';
import { useProvider, useSnapshot } from '@/composables/useSnapshot';
import { providerResourceRows } from '@/lib/providerProjection';
import { canViewProviderAssets } from '@/lib/requestFlowRoles';
import { getProductRole } from '@/composables/useProductRole';

// 供数侧「资源管理清单」（T9）：按生命周期浏览本部门已挂接资源全量行。纯 snapshot 投影、只读管理态——
// 不在左导航增项（守左导航场景页 ≤10 约束），由「供数据」概览卡点入。视图门=供数三岗位只读浏览
// （业务方 2026-06-09：操作员也需看本部门清单）；清单无行内管理动作。表壳复用 ProviderManageList。
const provider = useProvider();
const { source } = useSnapshot();
const role = getProductRole();
const canView = computed(() => canViewProviderAssets(role.value));
const rows = computed(() => providerResourceRows(provider.value as Record<string, unknown>));
const meta = computed(() => {
  if (source.value !== 'live') return '正在加载……';
  const n = rows.value.length;
  return n ? `本部门资源 ${n} 项（按生命周期浏览全部）` : '本部门暂无已挂接资源';
});
</script>

<template>
  <ProviderManageList
    title="资源管理清单"
    :meta="meta"
    :links="[
      { label: '提供方管理', href: '#/provider' },
      { label: '目录管理清单', href: '#/provider/catalogs' },
      { label: '资源挂接', href: '#/provider/wizard/hookup-submit' },
    ]"
    :columns="[
      { label: '资源名称', key: 'name' },
      { label: '所属目录', key: 'code', mono: true },
      { label: '类型', key: 'kind' },
      { label: '生命周期', key: 'status', pill: true },
    ]"
    :rows="rows"
    :loaded="source === 'live'"
    :can-view="canView"
    empty-text="本部门暂无已挂接资源。"
    empty-filtered-text="暂无匹配的资源数据"
    deny-text="当前岗位无资源管理视图权限。"
    testid="provider-resource-list"
  />
</template>
