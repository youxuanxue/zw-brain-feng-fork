<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailActions from '@/components/DetailActions.vue';
import { authFetch } from '@/composables/useAuth';
import { invokeActionStub, pushToast } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';
import { OBJECTION_TYPE_ZH } from '@/lib/objectionLabels';
import { apiUrl } from '@/composables/useApiBase';

interface CandidateOption {
  code: string;
  label: string;
  ownerOrgId?: string;
}

interface TargetTypeConfig {
  value: string;
  zh: string;
  hint: string;
  search: boolean;
  objectionKind: string;
}

const TARGET_TYPES: TargetTypeConfig[] = [
  { value: 'catalog', zh: OBJECTION_TYPE_ZH.catalog, hint: '从目录库选一条', search: true, objectionKind: 'catalog_quality' },
  { value: 'resource', zh: OBJECTION_TYPE_ZH.resource, hint: '从资源库选一条', search: true, objectionKind: 'resource_quality' },
  { value: 'delivery', zh: OBJECTION_TYPE_ZH.delivery, hint: '从交付任务选一条', search: true, objectionKind: 'usage' },
  { value: 'authorization', zh: OBJECTION_TYPE_ZH.authorization, hint: '手填授权 ID（不在已列举库内不校验）', search: false, objectionKind: 'authorization' },
  { value: 'content', zh: OBJECTION_TYPE_ZH.content, hint: '手填内容/记录 ID（如 record_id、字段内容指纹）', search: false, objectionKind: 'resource_quality' },
  { value: 'use', zh: OBJECTION_TYPE_ZH.use, hint: '手填使用上下文 ID（如调用编号、消费方任务 ID）', search: false, objectionKind: 'usage' },
  { value: 'alert', zh: OBJECTION_TYPE_ZH.alert, hint: '手填告警事件 ID', search: false, objectionKind: 'resource_quality' },
];

const role = getProductRole();
const route = useRoute();
// query string 预填：?type=<dim>&id=<x>&title=<...>
// P4 段「提资源异议」「提交付异议」入口跳来时一键带上上下文，避免用户手填
// 用 ref 初值赋好，避免 watch(targetType) 触发清空 targetId
const queryType = String(route.query.type ?? '');
const validQueryType = TARGET_TYPES.some((t) => t.value === queryType) ? queryType : 'catalog';
const title = ref(String(route.query.title ?? ''));
const targetType = ref<string>(validQueryType);
const targetId = ref(String(route.query.id ?? ''));
// 异议依据须用户亲笔填写真实理由；默认空白、用 placeholder 提示该填什么，不预置成品口径。
const basis = ref('');
const creating = ref(false);

const candidates = ref<CandidateOption[]>([]);
const candidatesLoading = ref(false);
const candidatesError = ref<string | null>(null);

const activeConfig = computed<TargetTypeConfig>(
  () => TARGET_TYPES.find((t) => t.value === targetType.value) ?? TARGET_TYPES[0],
);

// datalist 不分页 — 浏览器原生支持输入过滤；候选保留全部以便用户键入任意关键词命中
const candidatesByCode = computed(() => {
  const map = new Map<string, CandidateOption>();
  for (const c of candidates.value) map.set(c.code, c);
  return map;
});

const selectedCandidate = computed(() => candidatesByCode.value.get(targetId.value));
const selectedLabel = computed(() => selectedCandidate.value?.label ?? '');

async function loadCandidates() {
  candidates.value = [];
  candidatesError.value = null;
  if (!activeConfig.value.search) return;
  candidatesLoading.value = true;
  try {
    const skillByType: Record<string, { skill: string; code: string; label: string }> = {
      catalog: { skill: 'catalog.entry.query', code: 'catalog_code', label: 'title' },
      resource: { skill: 'resource.asset.query', code: 'resource_code', label: 'title' },
      delivery: { skill: 'delivery.list', code: 'delivery_code', label: 'name' },
    };
    const cfg = skillByType[targetType.value];
    if (!cfg) return;
    const resp = await authFetch(apiUrl(`/api/skills/${cfg.skill}`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ role: role.value, limit: 200, confirmed: true }),
    });
    if (!resp.ok) {
      const errBody = await resp.json().catch(() => ({}));
      if (resp.status === 403 || errBody.error === 'access_denied') {
        candidatesError.value = '当前岗位无权限列出候选；可手填对象编号，后端会校验存在。';
        return;
      }
      throw new Error('暂时无法加载候选对象，请稍后再试。');
    }
    const payload = (await resp.json()) as { items?: Record<string, unknown>[] };
    candidates.value = (payload.items ?? []).map((row) => ({
      code: String(row[cfg.code] ?? row.id ?? ''),
      label: String(row[cfg.label] ?? row.title ?? row.name ?? row[cfg.code] ?? ''),
      ownerOrgId: String(row.owner_org_id ?? row.ownerOrgId ?? '') || undefined,
    })).filter((c) => c.code);
  } catch (e) {
    candidatesError.value = e instanceof Error ? e.message : String(e);
  } finally {
    candidatesLoading.value = false;
  }
}

watch(targetType, () => {
  targetId.value = '';
  void loadCandidates();
});

onMounted(() => { void loadCandidates(); });

async function createObjection() {
  if (!title.value.trim() || !targetId.value.trim()) return;
  if (!basis.value.trim()) {
    pushToast({ kind: 'warn', title: '请填写异议依据', detail: '需要写明异议理由后才能创建。' });
    return;
  }
  creating.value = true;
  try {
    // complainant_org_id 不传，后端 create_case 缺省落 "unknown"（真实投诉方机构待身份集成后补）。
    // provider_org_id 仅在所选候选带 owner_org_id 时回填；手填类型（authorization/alert）或候选无
    // owner 元数据时留空，同样由后端落 "unknown"。
    const providerOrgId = selectedCandidate.value?.ownerOrgId || '';
    const payload: Record<string, unknown> = {
      objection_kind: activeConfig.value.objectionKind,
      target_type: targetType.value,
      target_id: targetId.value.trim(),
      title: title.value.trim(),
      basis_text: basis.value.trim(),
      evidence: [{ evidence_type: targetType.value, content_json: { source: 'p3-ui' } }],
    };
    if (providerOrgId) payload.provider_org_id = providerOrgId;
    const result = await invokeActionStub({
      skillId: 'objection.case.create',
      payload,
      successTitle: '异议已创建',
      refreshSnapshotAfter: true,
    });
    const data = result.data as Record<string, unknown> | undefined;
    const inner = (data?.result ?? data) as Record<string, unknown> | undefined;
    const newId = String(inner?.id ?? '');
    if (newId) {
      window.location.hash = `#/request-flow/objection/${newId}`;
    }
    // 失败时 invokeActionStub 内部已 toast；后端 InvalidStateError 返回错误信息
  } finally {
    creating.value = false;
  }
}
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/request-flow/objection">← 我的异议</a></nav>
    <section class="panel">
      <PageFocusHeader title="发起异议" meta="对象编号必须存在于库内；后端会拒绝凭空编号" />
      <div class="form-grid">
        <label for="title">异议标题</label>
        <input id="title" v-model="title" maxlength="100" placeholder="例如：字段描述与底册不一致" />

        <label for="ttype">对象类型</label>
        <select id="ttype" v-model="targetType">
          <option v-for="t in TARGET_TYPES" :key="t.value" :value="t.value">{{ t.zh }}</option>
        </select>

        <template v-if="activeConfig.search">
          <label for="target">对象编号</label>
          <input
            id="target"
            v-model="targetId"
            list="target-candidates"
            :placeholder="candidatesLoading ? '加载候选……' : '输入编号或标题搜索，或从下拉选'"
            autocomplete="off"
          />
          <datalist id="target-candidates">
            <option v-for="c in candidates" :key="c.code" :value="c.code">{{ c.label.slice(0, 60) }}</option>
          </datalist>
          <p v-if="candidatesError" class="form-hint warn">{{ candidatesError }}</p>
          <p v-else-if="!candidatesLoading && selectedLabel" class="form-hint ok">✓ 已选：{{ selectedLabel.slice(0, 60) }}</p>
          <p v-else-if="!candidatesLoading" class="form-hint">{{ activeConfig.hint }} · 共 {{ candidates.length }} 候选可下拉/输入过滤</p>
        </template>

        <template v-else>
          <label for="target">对象编号</label>
          <input id="target" v-model="targetId" placeholder="手填对象编号" />
          <p class="form-hint">{{ activeConfig.hint }}</p>
        </template>

        <label for="basis">异议依据</label>
        <textarea
          id="basis"
          v-model="basis"
          rows="4"
          maxlength="500"
          placeholder="例如：字段描述与底册不一致"
        />
      </div>
      <DetailActions>
        <button
          type="button"
          class="gov-btn gov-btn-primary"
          :disabled="creating || !title.trim() || !targetId.trim() || !basis.trim()"
          @click="createObjection"
        >
          创建异议
        </button>
      </DetailActions>
    </section>
  </main>
</template>

<style scoped>
.form-grid { display: grid; gap: 8px; max-width: 640px; margin-bottom: 12px; }
label { font-size: 13px; color: var(--b-muted, #5c6370); }
input, textarea, select {
  padding: 8px 10px; border: 1px solid var(--b-border, #d4e2f4); border-radius: 6px; font-size: 14px;
  background: #fff;
}
select:disabled { background: #f5f7fa; cursor: not-allowed; }
.form-hint { margin: 0; font-size: 12px; color: var(--b-text-secondary, #6b7280); }
.form-hint.warn { color: var(--b-warn, #b45309); }
.form-hint.ok { color: var(--b-success, #157a48); }
.gov-btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid transparent; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
</style>
