import { invokeActionStub, pushToast } from '@/composables/useActionStub';
import type { StructuredAction } from '@/composables/useNLAccelerator';

/**
 * NL 加速器结构化动作的统一消费口（原 P3RequestFlow / B11ComplianceOps / B12IntegrationAdmin
 * 三份拷贝抽出）。
 *
 * - `invoke`：真调用能力（照旧）。
 * - `filter` / `draft`：只是建议/提示，**不谎称「已应用」**——#278 修了撒谎的源（NL 路由那个
 *   假预填动作），本处修撒谎的汇（空操作却弹「已应用」）。真施加筛选属后续工作，本期诚实呈现。
 */
export function consumeNLAction(action: StructuredAction): void {
  if (action.kind === 'invoke' && action.target) {
    void invokeActionStub({ skillId: action.target, payload: action.payload, successTitle: action.label });
  } else if (action.kind === 'filter' || action.kind === 'draft') {
    pushToast({ kind: 'info', title: '建议', detail: action.label });
  }
}
