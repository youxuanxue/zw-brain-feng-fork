import { computed, ref, watch } from 'vue';
import { authFetch } from './useAuth';
import { apiUrl } from './useApiBase';
import { itemTypeLabel } from '@/lib/catalogCompileFields';

/**
 * 资源「字段数据模型」只读视图 — 接通 `metadata.schema.query` 能力。
 *
 * 该能力（live + webui，但此前在 zw-brain-web 无任何渲染消费者，登记在
 * scripts/webui_capability_rendered_exemptions.txt）返回某资源逐列的真实 schema
 * 快照（列名/中文注释/格式/长度/是否主键/是否可空/是否加密）。本期把它端到端铺到
 * P2 资源详情页，只读、无状态机、无 GATE。
 *
 * 后端权限：metadata.schema.query.execute → MANAGER / BUSIAUDIT / SECURITY_AUDIT。
 * OPERATER 无权——前端用 canPerformAction 在渲染前闸门（无权=不可见），不发请求。
 */

export interface SchemaColumn {
  /** 列名（英文标识，原样展示——这是数据模型字段名，非工程术语） */
  column: string;
  /** 中文注释/释义 */
  comment: string;
  /** 数据格式（legacy 原始类型 varchar/int 等；注册类型码经 itemTypeLabel 映射成业务标签） */
  format: string;
  /** 长度（无则空串） */
  length: string;
  isPrimaryKey: boolean;
  nullable: boolean;
  needEncrypt: boolean;
  // B2 字段级元数据扩展 3 列（键与写端 FIELD_METADATA_SNAPSHOT_KEYS 同名；
  // legacy 导入快照无这些键 → 空值，详情端按「有数据才显示列」处理，存量展示不回归）。
  /** 关联目录信息项（schema_json.catalog_item_id） */
  catalogItem: string;
  /** 是否更新主键（schema_json.is_up_id） */
  isUpdatePk: boolean;
  /** 是否更新时间（schema_json.is_up_time） */
  isUpdateTime: boolean;
  /** 数据标准（schema_json.meta_standard；legacy 兼回 meta_standard_cn） */
  metaStandard: string;
  /** 数据字典（schema_json.data_dict） */
  dataDict: string;
}

interface RawSnapshot {
  schema_json?: Record<string, unknown> | null;
}

function _str(v: unknown): string {
  if (v === null || v === undefined) return '';
  return String(v);
}

function _bool(v: unknown): boolean {
  // 后端用 0/1 表达布尔，也兼容 true/false。
  return v === 1 || v === '1' || v === true;
}

/** schema_json（逐列一条快照）→ 规范化列行；按 order_id 排序，过滤空列名。 */
export function normalizeSchemaColumns(items: readonly RawSnapshot[]): SchemaColumn[] {
  const rows: { order: number; col: SchemaColumn }[] = [];
  for (const it of items) {
    const sj = it?.schema_json;
    if (!sj || typeof sj !== 'object') continue;
    const rec = sj as Record<string, unknown>;
    const column = _str(rec.column_name);
    if (!column) continue;
    const order = Number(rec.order_id ?? 0) || 0;
    rows.push({
      order,
      col: {
        column,
        comment: _str(rec.comment) || _str(rec.remark),
        // 注册写入的是类型码（C/N/D/T）→ 映射成与注册输入同词的业务标签；
        // legacy 原始类型字符串（varchar 等）无码表命中、原样透出（不改写存量展示）。
        format: itemTypeLabel(_str(rec.format)),
        length: _str(rec.length),
        isPrimaryKey: _bool(rec.is_pk),
        // is_null=1 → 可空；is_null=0 → 必填（模板对 !nullable 显示「必填」）。
        nullable: _bool(rec.is_null),
        needEncrypt: _bool(rec.need_encrypt),
        catalogItem: _str(rec.catalog_item_id),
        isUpdatePk: _bool(rec.is_up_id),
        isUpdateTime: _bool(rec.is_up_time),
        metaStandard: _str(rec.meta_standard) || _str(rec.meta_standard_cn),
        dataDict: _str(rec.data_dict),
      },
    });
  }
  rows.sort((a, b) => a.order - b.order);
  return rows.map((r) => r.col);
}

export function useResourceSchema(
  resourceCode: () => string,
  enabled: () => boolean,
  role: () => string,
) {
  const columns = ref<SchemaColumn[]>([]);
  const loading = ref(false);
  const fetchError = ref<string | null>(null);
  const loaded = ref(false);

  async function load(code: string): Promise<void> {
    if (!code) return;
    loading.value = true;
    fetchError.value = null;
    loaded.value = false;
    try {
      const resp = await authFetch(
        // 缺陷 3 修复：必须经 apiUrl() 拼上部署前缀（/zw-brain/）。此前是全仓唯一漏拼前缀的
        // skills 调用 → 反代部署下请求落到 /api/skills/...（缺前缀）命不中路由 → 后端 404
        // （非真错，资源有无 schema 后端都返 200）。改用 apiUrl() 与其它 composable 对齐：
        // 有 schema 真展示，无 schema 走 isEmpty 诚实空态，零 404。
        apiUrl(
          `/api/skills/metadata.schema.query?role=${encodeURIComponent(role())}&resource_code=${encodeURIComponent(code)}`,
        ),
        { headers: { Accept: 'application/json' } },
      );
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const body = (await resp.json()) as Record<string, unknown>;
      const result = (body.result ?? body) as Record<string, unknown>;
      const items = Array.isArray(result.items) ? (result.items as RawSnapshot[]) : [];
      columns.value = normalizeSchemaColumns(items);
      loaded.value = true;
    } catch (e) {
      fetchError.value = e instanceof Error ? e.message : String(e);
      columns.value = [];
    } finally {
      loading.value = false;
    }
  }

  watch(
    () => [resourceCode(), enabled()] as const,
    ([code, on]) => {
      columns.value = [];
      fetchError.value = null;
      loaded.value = false;
      // 无权岗位不发请求（无权=不可见，由调用方一并隐藏整块）。
      if (on && code) void load(code);
    },
    { immediate: true },
  );

  // 诚实空态：仅在「已成功加载且确实零列」时为 true，避免把「加载中/失败」误显成「暂无」。
  const isEmpty = computed(() => loaded.value && !loading.value && !fetchError.value && columns.value.length === 0);

  return { columns, loading, fetchError, isEmpty };
}
