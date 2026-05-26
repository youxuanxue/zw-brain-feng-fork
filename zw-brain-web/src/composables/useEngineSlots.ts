// B1.2 三引擎 slot 容器：B1.2 UI 不重实装三引擎 admin 业务逻辑（实装在
// B13EnginesAdmin.vue 文件中，但路由已收编为 B1.2 子页 /integration-admin/engines，
// 不再作为独立主入口 B1.3）；本 composable 只提供 slot route 定义
// 让 B1.2 把"审批流 / 表单 / 推荐"作为 3 个跳转入口呈现给管理员，点击跳到三引擎
// 子页。href 通过 ?engine=<key> query 让落地页默认打开对应 tab。
//
// 与 E3 的协作约定：本 composable 列出的 3 个 slot key 是 contract；任何
// E3 admin route 变更（新增/重命名 admin 子路由 / 改 query 参数名）需双方对齐
// 后改这份 contract。

export interface EngineSlot {
  key: 'approval_flow' | 'form_schema' | 'recommendation';
  title: string;
  subtitle: string;
  href: string; // hash route + engine query，跳到 E3 已 land 的 admin 页并定位 tab
  status: 'available' | 'pending';
  pending_reason?: string;
}

export function useEngineSlots(): { slots: EngineSlot[] } {
  return {
    slots: [
      {
        key: 'approval_flow',
        title: '审批流配置',
        subtitle: '一句话描述项目级审批流程 → 自动生成节点 / 选人规则 / 条件分支 → 管理员确认入库',
        href: '#/integration-admin/engines?engine=approval_flow',
        status: 'available',
      },
      {
        key: 'form_schema',
        title: '表单配置',
        subtitle: '一句话描述申请表单 → 自动生成字段 schema → 管理员确认入库',
        href: '#/integration-admin/engines?engine=form_schema',
        status: 'available',
      },
      {
        key: 'recommendation',
        title: '智能推荐前置',
        subtitle: '推荐规则可视化配置 → 启停 + 灰度 + 回滚',
        href: '#/integration-admin/engines?engine=recommendation',
        status: 'available',
      },
    ],
  };
}
