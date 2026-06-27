<script setup lang="ts">
import { computed, onMounted, ref, watch, withDefaults } from 'vue';
import { useDeliveryTasks, useSnapshot } from '@/composables/useSnapshot';
import { authFetch } from '@/composables/useAuth';
import { apiUrl } from '@/composables/useApiBase';
import { getProductRole } from '@/composables/useProductRole';
import { filterByRouteAccess } from '@/lib/pageAccess';
import { myGrants, myRequests } from '@/lib/roleProjection';
import { canPlatformReviewRequests } from '@/lib/requestFlowRoles';
import { isTestMarkerName } from '@/lib/userLanguage';

type DeliveryEntryKey = 'mine' | 'grants' | 'tasks' | 'demands' | 'objections';

interface DeliveryEntry {
  key: DeliveryEntryKey;
  label: string;
  href: string;
  count?: number;
  testid?: string;
}

const props = withDefaults(
  defineProps<{
    active: DeliveryEntryKey;
    /** null = 组件内按 isApplicantRole 自决（P3 异议/供需页）；显式 false = 父级压掉（P4 纵深防御）。 */
    showApplicantTabs?: boolean | null;
    mineCount?: number;
    grantCount?: number;
    taskCount?: number;
    demandCount?: number;
    objectionCount?: number;
  }>(),
  { showApplicantTabs: null },
);

const role = getProductRole();
const tasks = useDeliveryTasks();
const { data: snapshot } = useSnapshot();
const loadedDemandCount = ref<number | undefined>(undefined);
const loadedObjectionCount = ref<number | undefined>(undefined);

// 与 P4Delivery 同源：受理岗不渲染「我的申请 / 我的授权」（纵深防御 + 动作语义一致）。
const isApplicantRole = computed(() => !canPlatformReviewRequests(role.value));
// Vue Boolean prop 省略时默认为 false（非 undefined），P3 页不传 prop 会误隐藏申请人 tab。
// null 默认 = 仅看 isApplicantRole；父级显式 false（受理岗）才压掉。
const showApplicantTabs = computed(
  () => isApplicantRole.value && (props.showApplicantTabs ?? true),
);

const defaultMineCount = computed(() => myRequests(snapshot.value).length);
const defaultGrantCount = computed(() => myGrants(snapshot.value).length);
const defaultTaskCount = computed(() => tasks.value.length);
const defaultDemandCount = computed(() => props.demandCount ?? loadedDemandCount.value);
const defaultObjectionCount = computed(() => props.objectionCount ?? loadedObjectionCount.value);

const applicantEntries = computed<DeliveryEntry[]>(() => {
  if (!showApplicantTabs.value) return [];
  return [
    { key: 'mine', label: '我的申请', href: '#/delivery-exchange?tab=mine', count: props.mineCount ?? defaultMineCount.value, testid: 'p4-view-mine' },
    { key: 'grants', label: '我的授权', href: '#/delivery-exchange?tab=grants', count: props.grantCount ?? defaultGrantCount.value, testid: 'p4-view-grants' },
  ];
});

const generalEntries = computed<DeliveryEntry[]>(() => {
  const all: DeliveryEntry[] = [
    { key: 'tasks', label: '交付任务', href: '#/delivery-exchange?tab=tasks', count: props.taskCount ?? defaultTaskCount.value, testid: 'p4-view-tasks' },
    { key: 'demands', label: '我的需求', href: '#/request-flow/supply-demand', count: defaultDemandCount.value },
    { key: 'objections', label: '我的异议', href: '#/request-flow/objection', count: defaultObjectionCount.value },
  ];
  return filterByRouteAccess(all, (it) => it.href, role.value);
});

const visibleEntries = computed(() => [...applicantEntries.value, ...generalEntries.value]);

async function refreshRemoteCounts() {
  const currentRole = role.value;
  const demandVisible = filterByRouteAccess([{ href: '#/request-flow/supply-demand' }], (it) => it.href, currentRole).length > 0;
  const objectionVisible = filterByRouteAccess([{ href: '#/request-flow/objection' }], (it) => it.href, currentRole).length > 0;

  if (props.demandCount === undefined && demandVisible) {
    const resp = await authFetch(apiUrl('/api/skills/demand.list'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ role: currentRole }),
    }).catch(() => null);
    if (resp?.ok) {
      const payload = (await resp.json().catch(() => ({}))) as { items?: unknown[] };
      loadedDemandCount.value = payload.items?.length ?? 0;
    }
  }

  if (props.objectionCount === undefined && objectionVisible) {
    const resp = await authFetch(apiUrl('/api/skills/objection.case.query'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ role: currentRole, confirmed: true }),
    }).catch(() => null);
    if (resp?.ok) {
      const payload = (await resp.json().catch(() => ({}))) as { items?: unknown[] };
      loadedObjectionCount.value = (payload.items ?? []).filter((row) => {
        const it = row as Record<string, unknown>;
        return !isTestMarkerName(String(it.title ?? it.topic ?? ''));
      }).length;
    }
  }
}

onMounted(() => { void refreshRemoteCounts(); });
watch(role, () => {
  loadedDemandCount.value = undefined;
  loadedObjectionCount.value = undefined;
  void refreshRemoteCounts();
});
</script>

<template>
  <nav class="delivery-entry-tabs" aria-label="领数据入口">
    <a
      v-for="entry in visibleEntries"
      :key="entry.key"
      class="delivery-entry-tab"
      :class="{ active: active === entry.key }"
      :href="entry.href"
      :data-testid="entry.key === 'mine' ? 'p4-view-mine' : entry.key === 'grants' ? 'p4-view-grants' : entry.testid"
    >
      <span>{{ entry.label }}</span>
      <strong v-if="entry.count !== undefined">{{ entry.count }}</strong>
    </a>
  </nav>
</template>

<style scoped>
.delivery-entry-tabs {
  display: flex;
  gap: 6px;
  margin: 4px 0 16px;
  border-bottom: 1px solid var(--b-border, #d4e2f4);
  overflow-x: auto;
}
.delivery-entry-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 38px;
  padding: 8px 16px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: none;
  color: var(--b-muted, #5c6370);
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  text-decoration: none;
  white-space: nowrap;
}
.delivery-entry-tab.active {
  border-bottom-color: var(--b-primary, #006be6);
  color: var(--b-primary, #006be6);
  font-weight: 600;
}
.delivery-entry-tab strong {
  color: inherit;
  font-size: 13px;
  line-height: 1;
}
</style>
