export const DATASOURCE_ENDPOINT_LIST_SKILL = 'datasource.endpoint.list';

export type DataPartition = 'front' | 'standard' | 'service';

export interface DatasourceEndpointRow {
  endpoint_id: string;
  connection_ref: string;
  display_name: string;
  db_name: string;
  db_type: string;
  host?: string | null;
  port?: number | null;
  org_code?: string | null;
  org_name?: string | null;
  contact_name?: string | null;
  contact_phone?: string | null;
  data_partition: DataPartition;
  connectivity_status: string;
  metadata_database_id?: string | null;
  resource_origin?: 'front' | 'landed';
  remark?: string | null;
}

const PARTITION_LABEL: Record<DataPartition, string> = {
  front: '前置库',
  standard: '标准库',
  service: '服务库',
};

const CONNECTIVITY_LABEL: Record<string, string> = {
  connected: '连通',
  disconnected: '未连通',
  unknown: '未探测',
  not_found: '不存在',
  ok: '连通',
  failed: '未连通',
};

const DB_TYPE_LABEL: Record<string, string> = {
  mysql: 'MySQL',
};

export function partitionLabel(partition: string): string {
  return PARTITION_LABEL[partition as DataPartition] ?? partition;
}

export function connectivityLabel(status: string): string {
  return CONNECTIVITY_LABEL[status] ?? status;
}

/** 连通性徽标样式：未知态中性，不制造「故障」焦虑。 */
export function connectivityTagClass(status: string): 'ok' | 'warn' | 'bad' {
  if (status === 'connected' || status === 'ok') return 'ok';
  if (status === 'unknown') return 'warn';
  return 'bad';
}

export function dbTypeLabel(dbType: string): string {
  return DB_TYPE_LABEL[dbType.toLowerCase()] ?? dbType;
}

export function formatDatasourceOptionLabel(row: DatasourceEndpointRow): string {
  return `${row.display_name}（${row.db_name} · ${partitionLabel(row.data_partition)}）`;
}

export function datasourceEndpointsFromProvider(provider: Record<string, unknown>): DatasourceEndpointRow[] {
  const raw = provider.datasource_endpoints;
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => item as Record<string, unknown>)
    .map((item) => ({
      endpoint_id: String(item.endpoint_id ?? ''),
      connection_ref: String(item.connection_ref ?? ''),
      display_name: String(item.display_name ?? item.endpoint_id ?? ''),
      db_name: String(item.db_name ?? ''),
      db_type: String(item.db_type ?? 'mysql'),
      host: item.host != null ? String(item.host) : null,
      port: typeof item.port === 'number' ? item.port : item.port != null ? Number(item.port) : null,
      org_code: item.org_code != null ? String(item.org_code) : null,
      org_name: item.org_name != null ? String(item.org_name) : null,
      contact_name: item.contact_name != null ? String(item.contact_name) : null,
      contact_phone: item.contact_phone != null ? String(item.contact_phone) : null,
      data_partition: (item.data_partition as DataPartition) ?? 'front',
      connectivity_status: String(item.connectivity_status ?? 'unknown'),
      metadata_database_id: item.metadata_database_id != null ? String(item.metadata_database_id) : null,
      resource_origin: (item.resource_origin === 'landed' ? 'landed' : 'front') as 'front' | 'landed',
      remark: item.remark != null ? String(item.remark) : null,
    }))
    .filter((row) => row.endpoint_id);
}

export function endpointsForOrigin(
  rows: DatasourceEndpointRow[],
  origin: 'front' | 'landed',
): DatasourceEndpointRow[] {
  if (origin === 'front') {
    return rows.filter((r) => r.data_partition === 'front' || r.resource_origin === 'front');
  }
  return rows.filter((r) => r.data_partition === 'standard' || r.data_partition === 'service' || r.resource_origin === 'landed');
}
