/** 异议（objection）写动作的单一事实源 — P5 收件箱/详情等多个调用点共用同一口径，
 *  避免 skillId / 成功文案 / payload 形状在各页手抄后漂移（同一信息存两处需手同步=反简洁）。
 *  注：工作台行内受理走后端投影 `_objection_item` 派生 payload + 通用 ActionPanel，不经此处。 */
import { invokeActionStub } from '@/composables/useActionStub';

/** 受理异议（objection.case.accept）：submitted → 进入平台核查。受理后刷新快照。 */
export async function acceptObjectionCase(objectionId: string) {
  return invokeActionStub({
    skillId: 'objection.case.accept',
    payload: { objection_id: objectionId },
    successTitle: '异议已受理，进入核查',
    refreshSnapshotAfter: true,
  });
}
