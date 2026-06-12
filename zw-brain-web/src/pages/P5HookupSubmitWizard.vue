<script setup lang="ts">
import { computed, ref } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailActions from '@/components/DetailActions.vue';
import { invokeActionStub } from '@/composables/useActionStub';
import {
  SHARE_TYPE_OPTIONS,
  OPEN_TYPE_OPTIONS,
  UPDATE_CYCLE_OPTIONS,
  DATA_PROVISION_OPTIONS,
  FILE_STORE_OPTIONS,
  ITEM_TYPE_OPTIONS,
  blankResourceFieldColumn,
  resourceFieldColumnToPayload,
  type ResourceFieldColumnDraft,
} from '@/lib/catalogCompileFields';

// J2 资源挂接（提交侧）— 为已发布目录补挂 库表 / 文件 物化资源。
// 只做 table / file 两形态；接口资源走「代理服务注册向导」入口（不重复造）。
// 调 resource.mount.{table,file}.prepare 建草稿 → resource.asset.submit_review 提交复核。

type Kind = 'table' | 'file';
const kind = ref<Kind>('table');

const catalogCode = ref('');
const resourceCode = ref('');
const title = ref('');
const ownerOrgId = ref('');

// B2：资源注册业务信息（对标旧平台资源「基本信息」标签页，table/file 共用）。
// 注：旧平台库表资源注册第一屏只有「开放类型」无「开放条件」（T4 已删 openCondition）。
const shareType = ref('2'); // 共享类型
const shareCondition = ref(''); // 共享条件
const openType = ref('3'); // 开放类型
const resourceDesc = ref(''); // 资源描述
const sourceSystem = ref(''); // 来源系统
const resourceVersion = ref(''); // 版本号
const techContact = ref(''); // 技术联系人
const contactPhone = ref(''); // 联系方式

// 库表（口令不在挂接期收集——挂接只记连接标识，连通性 not_probed 待发布激活时连同凭据校验，
// 不收集一个当场丢弃的 secret）
// 库表资源注册补齐字段（T4，对标旧平台 data_resource 权威字段集）：资源所处位置 / 数据提供方式
// （周期·一次性）/ 资源更新周期。采集端与详情端 _table_section 双向对齐。
const resLocation = ref(''); // 资源所处位置
const dataProvisionMethod = ref('periodic'); // 数据提供方式（周期/一次性）
const resUpdateCycle = ref('2'); // 资源更新周期（库表侧；文件侧用 updateFrequency）
const tableName = ref('');
const connHost = ref('');
const connDatabase = ref('');

// B2 字段数据模型逐列登记（10 列，对标旧平台 dc_resource_table_column；取代旧「源→目标」
// 两列映射）。主行 = 高频 6 列（字段名/释义/类型/长度/主键/可空）；低频 5 列（关联目录
// 信息项/更新主键/更新时间/数据标准/数据字典）收进每行「更多」展开区——不做横向巨表
// （0611「单条信息项尽量同一行」同类口径：一字段一行，低频列不挤爆行宽）。
interface FieldRow extends ResourceFieldColumnDraft {
  showMore: boolean;
}
function blankFieldRow(): FieldRow {
  return { ...blankResourceFieldColumn(), showMore: false };
}
const fieldRows = ref<FieldRow[]>([blankFieldRow()]);

// 文件
const fileName = ref('');
const accessPath = ref('');
const contentHash = ref('');
const updateFrequency = ref('daily');
// B2：文件格式/大小/存储类型 → 让资源详情「文件信息」标签页有值（采集端与详情端对齐）。
const fileFormat = ref('');
const fileSize = ref('');
const fileStoreType = ref('centerStore');

const submitting = ref(false);

// 字段登记完整性 —— 操作员责任面，红/绿实时回显（库表必填：每行需有字段名；文件可选）。
const fieldReady = computed(
  () => fieldRows.value.length > 0 && fieldRows.value.every((row) => row.columnName.trim()),
);

const canPrepare = computed(() => Boolean(catalogCode.value.trim() && resourceCode.value.trim()));

function addFieldRow() {
  fieldRows.value.push(blankFieldRow());
}
function removeFieldRow(i: number) {
  fieldRows.value.splice(i, 1);
}

function buildPayload(): Record<string, unknown> {
  // 共享/开放属性 → 后端 access_policy_json；业务信息 → summary_json。空值传 undefined，
  // 后端落 None、详情端诚实空态展示「未提供」（禁造假）。
  const business = {
    shared_type: shareType.value || undefined,
    shared_condition: shareCondition.value.trim() || undefined,
    open_type: openType.value || undefined,
    resource_desc: resourceDesc.value.trim() || undefined,
    source_system: sourceSystem.value.trim() || undefined,
    resource_version: resourceVersion.value.trim() || undefined,
    tech_contact: techContact.value.trim() || undefined,
    contact_phone: contactPhone.value.trim() || undefined,
  };
  const base = {
    resource_code: resourceCode.value.trim(),
    catalog_code: catalogCode.value.trim(),
    title: title.value.trim() || resourceCode.value.trim(),
    owner_org_id: ownerOrgId.value.trim() || undefined,
    ...business,
  };
  // B2：字段级元数据 10 列 → 后端 field_columns（写入字段快照，与存量导入同源同形，
  // 详情「字段数据模型」逐列回显）。无字段名的行不上送（后端同口径再滤一道）。
  const fieldColumns = fieldRows.value
    .filter((row) => row.columnName.trim())
    .map((row) => resourceFieldColumnToPayload(row));
  if (kind.value === 'table') {
    return {
      ...base,
      // 库表注册业务字段（T4）：资源所处位置 / 数据提供方式 / 资源更新周期 → 后端
      // _business_summary，详情端「库表信息」回显。
      res_location: resLocation.value.trim() || undefined,
      data_provision_method: dataProvisionMethod.value || undefined,
      update_cycle: resUpdateCycle.value || undefined,
      table_name: tableName.value.trim(),
      connection: { host: connHost.value.trim(), database: connDatabase.value.trim() },
      field_columns: fieldColumns,
    };
  }
  return {
    ...base,
    file_name: fileName.value.trim(),
    access_path: accessPath.value.trim(),
    content_hash: contentHash.value.trim() || undefined,
    update_frequency: updateFrequency.value,
    file_format: fileFormat.value.trim() || undefined,
    file_size: fileSize.value.trim() || undefined,
    file_store_type: fileStoreType.value || undefined,
    // 文件字段登记可选（结构化文件可逐列登记；不登记不拦提交）。
    field_columns: fieldColumns,
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
      <PageFocusHeader title="资源挂接向导" meta="为已发布目录补挂 库表 / 文件 物化资源（接口资源走「代理服务注册向导」）" />

      <!-- C2（0605#4 截图）：标签与切换器同行，避免内容宽度的切换器单独占一行、
           右侧留出大片空白带的观感问题（资源类型已收敛为 库表/文件，API 走独立入口）。 -->
      <div class="seg-row">
        <label class="field-label">物化形式</label>
        <div class="seg">
          <button type="button" class="seg-btn" :class="{ active: kind === 'table' }" @click="kind = 'table'">库表</button>
          <button type="button" class="seg-btn" :class="{ active: kind === 'file' }" @click="kind = 'file'">文件</button>
        </div>
      </div>

      <div class="grid2">
        <div><label class="field-label">所属数据目录 *</label><input v-model="catalogCode" class="gov-input" placeholder="挂接到哪个已发布目录" /></div>
        <div><label class="field-label">资源标识 *</label><input v-model="resourceCode" class="gov-input" placeholder="本资源的唯一标识" /></div>
        <div><label class="field-label">资源名称</label><input v-model="title" class="gov-input" placeholder="例如：养老资源信息" /></div>
        <div><label class="field-label">归属机构</label><input v-model="ownerOrgId" class="gov-input" placeholder="须与目标目录归属一致（否则挂接被拒）" /></div>
      </div>

      <!-- B2 资源基本信息（对标旧平台资源注册「基本信息」标签页，库表/文件共用） -->
      <h3 class="block-title">资源基本信息</h3>
      <div class="grid2">
        <div>
          <label class="field-label">共享类型</label>
          <select v-model="shareType" class="gov-input">
            <option v-for="o in SHARE_TYPE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
          </select>
        </div>
        <div>
          <label class="field-label">开放类型</label>
          <select v-model="openType" class="gov-input">
            <option v-for="o in OPEN_TYPE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
          </select>
        </div>
        <div><label class="field-label">共享条件</label><input v-model="shareCondition" class="gov-input" placeholder="例如：根据个人信息保护要求授权共享" /></div>
        <div><label class="field-label">来源系统</label><input v-model="sourceSystem" class="gov-input" placeholder="例如：养老保险建模系统" /></div>
        <div><label class="field-label">版本号</label><input v-model="resourceVersion" class="gov-input" placeholder="例如：V2.0" /></div>
        <div><label class="field-label">技术联系人</label><input v-model="techContact" class="gov-input" placeholder="例如：王四" /></div>
        <div><label class="field-label">联系方式</label><input v-model="contactPhone" class="gov-input" placeholder="例如：17890786758" /></div>
        <div class="span2"><label class="field-label">资源描述</label><input v-model="resourceDesc" class="gov-input" placeholder="一句话说明本资源的数据内容" /></div>
      </div>

      <!-- 库表 -->
      <template v-if="kind === 'table'">
        <!-- T4：库表资源注册补齐字段（资源所处位置 / 数据提供方式 / 资源更新周期），与详情「库表信息」对齐 -->
        <div class="grid2">
          <div><label class="field-label">资源所处位置</label><input v-model="resLocation" class="gov-input" placeholder="例如：省政务云 · 共享交换区" /></div>
          <div>
            <label class="field-label">数据提供方式</label>
            <select v-model="dataProvisionMethod" class="gov-input">
              <option v-for="o in DATA_PROVISION_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
          </div>
          <div>
            <label class="field-label">资源更新周期</label>
            <select v-model="resUpdateCycle" class="gov-input">
              <option v-for="o in UPDATE_CYCLE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
          </div>
        </div>
        <div class="grid2">
          <div><label class="field-label">表名</label><input v-model="tableName" class="gov-input" placeholder="t_xxx" /></div>
          <div><label class="field-label">库主机</label><input v-model="connHost" class="gov-input" placeholder="host" /></div>
          <div><label class="field-label">库名</label><input v-model="connDatabase" class="gov-input" placeholder="database" /></div>
        </div>

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
          <div><label class="field-label">文件格式</label><input v-model="fileFormat" class="gov-input" placeholder="例如：docx" /></div>
          <div><label class="field-label">文件大小（字节）</label><input v-model="fileSize" class="gov-input" placeholder="例如：17869" /></div>
          <div>
            <label class="field-label">存储类型</label>
            <select v-model="fileStoreType" class="gov-input">
              <option v-for="o in FILE_STORE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
          </div>
        </div>
        <p class="status-line neutral">文件完整性：⏳ 挂接时记录内容指纹，发布激活时校验</p>
      </template>

      <!-- B2 字段数据模型逐列登记（与详情页「字段数据模型」同词同列，一词一概念）。
           主行 6 高频列；低频 5 列收进每行「更多」——不做横向巨表。 -->
      <h3 class="block-title">字段数据模型（逐列登记）</h3>
      <p class="block-hint">
        {{ kind === 'table'
          ? '逐行登记库表字段及其元数据（对标旧平台信息项维护表格）。字段名必填；关联目录信息项、更新标识、数据标准与数据字典在「更多」里登记。'
          : '结构化文件（如表格类）可按需逐行登记字段，登记后详情页同样回显；不登记不影响提交。' }}
      </p>
      <div class="field-table-wrap">
        <table class="field-table" data-testid="hookup-field-table">
          <thead>
            <tr>
              <th class="col-name">字段名（英文）<span v-if="kind === 'table'" class="req">*</span></th>
              <th class="col-name">释义（中文名）</th>
              <th>字段类型</th>
              <th class="col-narrow">长度精度</th>
              <th class="col-flag">主键</th>
              <th class="col-flag">可空</th>
              <th class="col-ops">操作</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="(row, i) in fieldRows" :key="i">
              <tr>
                <td><input v-model="row.columnName" class="gov-input cell-input" placeholder="例如：xm" /></td>
                <td><input v-model="row.comment" class="gov-input cell-input" placeholder="例如：姓名" /></td>
                <td>
                  <select v-model="row.format" class="gov-input cell-input">
                    <option v-for="o in ITEM_TYPE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
                  </select>
                </td>
                <td><input v-model="row.length" class="gov-input cell-input" placeholder="50" /></td>
                <td class="cell-center">
                  <input v-model="row.isPk" type="checkbox" class="cell-check" :aria-label="`字段 ${i + 1} 是否主键`" />
                </td>
                <td class="cell-center">
                  <input v-model="row.isNull" type="checkbox" class="cell-check" :aria-label="`字段 ${i + 1} 是否可空`" />
                </td>
                <td class="cell-ops">
                  <button type="button" class="link-btn" :data-testid="`field-more-btn-${i}`" @click="row.showMore = !row.showMore">
                    {{ row.showMore ? '收起' : '更多' }}
                  </button>
                  <button type="button" class="link-btn danger" :disabled="fieldRows.length <= 1" @click="removeFieldRow(i)">删除</button>
                </td>
              </tr>
              <tr v-if="row.showMore" class="field-more-row">
                <td :colspan="7">
                  <div class="more-grid">
                    <div>
                      <label class="field-label">关联目录信息项</label>
                      <input v-model="row.catalogItemId" class="gov-input" placeholder="该字段对应的目录信息项（可不填）" />
                    </div>
                    <div>
                      <label class="field-label">数据标准</label>
                      <input v-model="row.metaStandard" class="gov-input" placeholder="例如：GB/T 2261.1" />
                    </div>
                    <div>
                      <label class="field-label">数据字典</label>
                      <input v-model="row.dataDict" class="gov-input" placeholder="例如：性别代码表" />
                    </div>
                    <div class="more-flags">
                      <label class="check-inline">
                        <input v-model="row.isUpId" type="checkbox" :aria-label="`字段 ${i + 1} 是否更新主键`" /> 更新主键
                      </label>
                      <label class="check-inline">
                        <input v-model="row.isUpTime" type="checkbox" :aria-label="`字段 ${i + 1} 是否更新时间`" /> 更新时间
                      </label>
                    </div>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
      <button type="button" class="gov-btn gov-btn-secondary add-field" @click="addFieldRow">+ 增加字段</button>

      <!-- 字段登记完整性：操作员责任面，红/绿（仅库表为提交门；文件可选不拦） -->
      <p v-if="kind === 'table'" class="status-line" :class="fieldReady ? 'ok' : 'bad'">
        字段登记完整性：{{ fieldReady ? '✓ 已就绪（可提交复核）' : '✗ 未就绪（每行需填字段名）' }}
      </p>

      <DetailActions>
        <button type="button" class="gov-btn gov-btn-secondary" :disabled="!canPrepare || submitting" @click="saveDraft">保存草稿</button>
        <button type="button" class="gov-btn gov-btn-primary" :disabled="!canPrepare || submitting || (kind === 'table' && !fieldReady)" @click="submitReview">提交复核</button>
      </DetailActions>
    </section>
  </main>
</template>

<style scoped>
.field-label { display: block; font-size: 13px; margin-bottom: 6px; color: var(--b-muted, #5c6370); }
.gov-input { width: 100%; padding: 6px 10px; border-radius: 6px; border: 1px solid var(--b-border, #d4e2f4); box-sizing: border-box; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 12px; }
.grid2 .span2 { grid-column: 1 / -1; }
.block-title { margin: 16px 0 10px; font-size: 14px; font-weight: 600; color: var(--b-text, #1f2733); }
.seg-row { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.seg-row .field-label { margin: 0; }
.seg { display: inline-flex; border: 1px solid var(--b-border, #d4e2f4); border-radius: 6px; overflow: hidden; }
.seg-btn { padding: 6px 18px; border: none; background: #fff; cursor: pointer; font-size: 13px; }
.seg-btn.active { background: var(--b-primary, #006be6); color: #fff; }
.block-hint { font-size: 12px; color: var(--b-muted, #5c6370); margin: 0 0 10px; }
.field-table-wrap { overflow-x: auto; margin-bottom: 8px; }
.field-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.field-table th { text-align: left; padding: 6px 8px; color: var(--b-muted, #5c6370); font-weight: 500; border-bottom: 1px solid var(--b-border, #d4e2f4); white-space: nowrap; }
.field-table td { padding: 6px 8px; vertical-align: middle; }
.field-table .col-name { min-width: 140px; }
.field-table .col-narrow { width: 90px; }
.field-table .col-flag { width: 48px; text-align: center; }
.field-table .col-ops { width: 110px; }
.cell-input { width: 100%; }
.cell-center { text-align: center; }
.cell-check { width: 16px; height: 16px; }
.cell-ops { white-space: nowrap; }
.link-btn { background: none; border: none; color: var(--b-primary, #006be6); cursor: pointer; font-size: 13px; padding: 2px 4px; }
.link-btn:disabled { color: var(--b-muted, #5c6370); opacity: 0.5; cursor: not-allowed; }
.link-btn.danger { color: #c0392b; }
.field-more-row td { background: var(--b-bg-soft, #f6f9fe); border-bottom: 1px solid var(--b-border, #d4e2f4); }
.more-grid { display: grid; grid-template-columns: 1fr 1fr 1fr auto; gap: 12px; align-items: end; padding: 4px 2px 8px; }
.more-flags { display: flex; gap: 14px; padding-bottom: 8px; }
.check-inline { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; color: var(--b-text, #1f2733); white-space: nowrap; }
.req { color: #c0392b; margin-left: 2px; }
.add-field { margin-bottom: 12px; }
.status-line { font-size: 13px; margin: 8px 0; }
.status-line.ok { color: #1a7f37; }
.status-line.bad { color: #c0392b; }
.status-line.neutral { color: var(--b-muted, #5c6370); }
.gov-btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid transparent; margin-right: 8px; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.gov-btn-secondary { background: #fff; border-color: var(--b-border, #d4e2f4); }
</style>
