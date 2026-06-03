<script setup lang="ts">
import { computed, ref } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailActions from '@/components/DetailActions.vue';
import { invokeActionStub } from '@/composables/useActionStub';

// J2 资源挂接（提交侧）— 为已发布目录补挂 库表 / 文件 物化资源。
// 只做 table / file 两形态；api 走既有「API 服务化」入口（不重复造）。
// 调 resource.mount.{table,file}.prepare 建草稿 → resource.asset.submit_review 提交复核。

type Kind = 'table' | 'file';
const kind = ref<Kind>('table');

const catalogCode = ref('');
const resourceCode = ref('');
const title = ref('');
const ownerOrgId = ref('');

// 库表（口令不在挂接期收集——挂接只记连接标识，连通性 not_probed 待发布激活时连同凭据校验，
// 不收集一个当场丢弃的 secret）
const tableName = ref('');
const connHost = ref('');
const connDatabase = ref('');
const mappings = ref<{ source: string; target: string }[]>([{ source: '', target: '' }]);

// 文件
const fileName = ref('');
const accessPath = ref('');
const contentHash = ref('');
const updateFrequency = ref('daily');

const submitting = ref(false);

// 字段映射完整性 —— 操作员责任面，红/绿实时回显。
const mappingReady = computed(
  () => kind.value === 'table' && mappings.value.length > 0 && mappings.value.every((m) => m.source.trim() && m.target.trim()),
);

const canPrepare = computed(() => Boolean(catalogCode.value.trim() && resourceCode.value.trim()));

function addMapping() {
  mappings.value.push({ source: '', target: '' });
}
function removeMapping(i: number) {
  mappings.value.splice(i, 1);
}

function buildPayload(): Record<string, unknown> {
  const base = {
    resource_code: resourceCode.value.trim(),
    catalog_code: catalogCode.value.trim(),
    title: title.value.trim() || resourceCode.value.trim(),
    owner_org_id: ownerOrgId.value.trim() || undefined,
  };
  if (kind.value === 'table') {
    return {
      ...base,
      table_name: tableName.value.trim(),
      connection: { host: connHost.value.trim(), database: connDatabase.value.trim() },
      field_mappings: mappings.value.filter((m) => m.source.trim() && m.target.trim()),
    };
  }
  return {
    ...base,
    file_name: fileName.value.trim(),
    access_path: accessPath.value.trim(),
    content_hash: contentHash.value.trim() || undefined,
    update_frequency: updateFrequency.value,
  };
}

async function saveDraft() {
  if (!canPrepare.value) return;
  submitting.value = true;
  try {
    await invokeActionStub({
      skillId: kind.value === 'table' ? 'resource.mount.table.prepare' : 'resource.mount.file.prepare',
      payload: buildPayload(),
      successTitle: '已保存挂接草稿',
    });
  } finally {
    submitting.value = false;
  }
}

async function submitReview() {
  if (!canPrepare.value) return;
  submitting.value = true;
  try {
    const prepared = await invokeActionStub({
      skillId: kind.value === 'table' ? 'resource.mount.table.prepare' : 'resource.mount.file.prepare',
      payload: buildPayload(),
      successTitle: '挂接草稿已保存',
      refreshSnapshotAfter: false,
    });
    if (!prepared.ok) return;
    await invokeActionStub({
      skillId: 'resource.asset.submit_review',
      payload: { resource_code: resourceCode.value.trim() },
      successTitle: '已提交复核',
    });
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/provider">← 提供方管理</a></nav>
    <section class="panel">
      <PageFocusHeader title="资源挂接向导" meta="为已发布目录补挂 库表 / 文件 物化资源（API 走「API 服务化」入口）" />

      <label class="field-label">物化形式</label>
      <div class="seg">
        <button type="button" class="seg-btn" :class="{ active: kind === 'table' }" @click="kind = 'table'">库表</button>
        <button type="button" class="seg-btn" :class="{ active: kind === 'file' }" @click="kind = 'file'">文件</button>
      </div>

      <div class="grid2">
        <div><label class="field-label">目标目录编码 *</label><input v-model="catalogCode" class="gov-input" placeholder="catalog_code" /></div>
        <div><label class="field-label">资源编码 *</label><input v-model="resourceCode" class="gov-input" placeholder="resource_code" /></div>
        <div><label class="field-label">资源名称</label><input v-model="title" class="gov-input" placeholder="资源名称" /></div>
        <div><label class="field-label">归属机构编码</label><input v-model="ownerOrgId" class="gov-input" placeholder="须与目标目录归属一致（否则挂接被拒）" /></div>
      </div>

      <!-- 库表 -->
      <template v-if="kind === 'table'">
        <div class="grid2">
          <div><label class="field-label">表名</label><input v-model="tableName" class="gov-input" placeholder="t_xxx" /></div>
          <div><label class="field-label">库主机</label><input v-model="connHost" class="gov-input" placeholder="host" /></div>
          <div><label class="field-label">库名</label><input v-model="connDatabase" class="gov-input" placeholder="database" /></div>
        </div>

        <label class="field-label">字段映射（源 → 目标）</label>
        <div v-for="(m, i) in mappings" :key="i" class="map-row">
          <input v-model="m.source" class="gov-input" placeholder="源字段" />
          <span class="arrow">→</span>
          <input v-model="m.target" class="gov-input" placeholder="目标字段" />
          <button type="button" class="gov-btn gov-btn-secondary" @click="removeMapping(i)" :disabled="mappings.length <= 1">删</button>
        </div>
        <button type="button" class="gov-btn gov-btn-secondary add-map" @click="addMapping">+ 加一行映射</button>

        <!-- 字段映射完整性：操作员责任面，红/绿 -->
        <p class="status-line" :class="mappingReady ? 'ok' : 'bad'">
          字段映射完整性：{{ mappingReady ? '✓ 已就绪（可提交复核）' : '✗ 未就绪（每行需填源 + 目标）' }}
        </p>
        <!-- 库连通性：部署期才能探，中性「待激活」，不传染「没做完」焦虑 -->
        <p class="status-line neutral">库连通性：⏳ 已记录连接配置，将在发布激活时校验连通</p>
      </template>

      <!-- 文件 -->
      <template v-else>
        <div class="grid2">
          <div><label class="field-label">文件名</label><input v-model="fileName" class="gov-input" placeholder="students.csv" /></div>
          <div><label class="field-label">访问路径</label><input v-model="accessPath" class="gov-input" placeholder="/data/xxx.csv" /></div>
          <div><label class="field-label">内容指纹（可选）</label><input v-model="contentHash" class="gov-input" placeholder="sha256:..." /></div>
          <div>
            <label class="field-label">更新频率</label>
            <select v-model="updateFrequency" class="gov-input">
              <option value="realtime">实时</option>
              <option value="daily">每日</option>
              <option value="weekly">每周</option>
              <option value="monthly">每月</option>
            </select>
          </div>
        </div>
        <p class="status-line neutral">文件完整性：⏳ 挂接时记录内容指纹，发布激活时校验</p>
      </template>

      <DetailActions>
        <button type="button" class="gov-btn gov-btn-secondary" :disabled="!canPrepare || submitting" @click="saveDraft">保存草稿</button>
        <button type="button" class="gov-btn gov-btn-primary" :disabled="!canPrepare || submitting || (kind === 'table' && !mappingReady)" @click="submitReview">提交复核</button>
      </DetailActions>
    </section>
  </main>
</template>

<style scoped>
.field-label { display: block; font-size: 13px; margin-bottom: 6px; color: var(--b-muted, #5c6370); }
.gov-input { width: 100%; padding: 6px 10px; border-radius: 6px; border: 1px solid var(--b-border, #d4e2f4); box-sizing: border-box; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 12px; }
.seg { display: inline-flex; margin-bottom: 16px; border: 1px solid var(--b-border, #d4e2f4); border-radius: 6px; overflow: hidden; }
.seg-btn { padding: 6px 18px; border: none; background: #fff; cursor: pointer; font-size: 13px; }
.seg-btn.active { background: var(--b-primary, #006be6); color: #fff; }
.map-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.map-row .gov-input { flex: 1; }
.arrow { color: var(--b-muted, #5c6370); }
.add-map { margin-bottom: 12px; }
.status-line { font-size: 13px; margin: 8px 0; }
.status-line.ok { color: #1a7f37; }
.status-line.bad { color: #c0392b; }
.status-line.neutral { color: var(--b-muted, #5c6370); }
.gov-btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid transparent; margin-right: 8px; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.gov-btn-secondary { background: #fff; border-color: var(--b-border, #d4e2f4); }
</style>
