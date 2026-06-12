import { invokeActionStub, pushToast } from '@/composables/useActionStub';

/** F4 文件资源受控下载（P4Delivery 列表 / P4DeliveryTaskDetail 详情共用，toast 文案单源）。
 *
 * 登记受控下载请求 + 落下载日志（文件名/大小/时间/领取方，对齐旧 resource_file_download_log）。
 * zw-brain 仅持有文件元数据；文件字节由源存储交付——与 F6 库表交换同属外部数据治理底座边界
 * （架构 §3.4）。本期诚实：仅当源存储返回真实可直达地址（http/https）才跳转下载，否则如实
 * 告知「经源存储交付、对接中」，不把内部受控锚伪造成直链。
 */
export async function downloadDeliveryFile(taskId: string, fileName: string): Promise<void> {
  const res = await invokeActionStub({
    skillId: 'delivery.file.download',
    payload: { task_id: taskId, file_name: fileName },
    successTitle: '已登记文件下载请求',
  });
  if (!res.ok) return;
  const root = (res.data ?? {}) as Record<string, unknown>;
  const inner = (root.result ?? root) as Record<string, unknown>;
  const link = String(inner.file_link ?? '');
  if (/^https?:\/\//i.test(link)) {
    window.open(link, '_blank', 'noopener');
    return;
  }
  pushToast({
    kind: 'info',
    title: '下载请求已登记',
    detail: '已记录受控下载日志（文件名 / 大小 / 时间 / 领取方）。文件内容由源存储交付，平台正在对接，完成后即可直接下载。',
  });
}
