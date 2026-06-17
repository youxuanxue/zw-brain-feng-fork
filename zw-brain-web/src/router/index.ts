import { createRouter, createWebHashHistory, type RouteRecordRaw } from 'vue-router';
import { getProductRole } from '@/composables/useProductRole';
import { pushToast } from '@/composables/useActionStub';
import { defaultRouteForRole, isRouteAllowedForRole } from '@/lib/pageAccess';
import P1Workbench from '@/pages/P1Workbench.vue';
import P2Discovery from '@/pages/P2Discovery.vue';
import P2ResourceDetail from '@/pages/P2ResourceDetail.vue';
import P2CatalogBrowse from '@/pages/P2CatalogBrowse.vue';
import P2CatalogDetail from '@/pages/P2CatalogDetail.vue';
import P3RequestDetail from '@/pages/P3RequestDetail.vue';
import P3ReviewDetail from '@/pages/P3ReviewDetail.vue';
import P3ObjectionInbox from '@/pages/P3ObjectionInbox.vue';
import P3ObjectionDetail from '@/pages/P3ObjectionDetail.vue';
import P3ObjectionNew from '@/pages/P3ObjectionNew.vue';
import P3SupplyDemand from '@/pages/P3SupplyDemand.vue';
import P4Delivery from '@/pages/P4Delivery.vue';
import P4Credential from '@/pages/P4Credential.vue';
import P4DeliveryTaskDetail from '@/pages/P4DeliveryTaskDetail.vue';
import P5Provider from '@/pages/P5Provider.vue';
import P5NationalExtElem from '@/pages/P5NationalExtElem.vue';
import P5InlineCatalogWizard from '@/pages/P5InlineCatalogWizard.vue';
import P5CatalogManageList from '@/pages/P5CatalogManageList.vue';
import P5ResourceManageList from '@/pages/P5ResourceManageList.vue';
import P5CatalogReviewInbox from '@/pages/P5CatalogReviewInbox.vue';
import P5ReverseCatalogWizard from '@/pages/P5ReverseCatalogWizard.vue';
import P5ApiServiceWizard from '@/pages/P5ApiServiceWizard.vue';
import P5HookupSubmitWizard from '@/pages/P5HookupSubmitWizard.vue';
import P5QualityRuleWizard from '@/pages/P5QualityRuleWizard.vue';
import P5FieldDecisionInbox from '@/pages/P5FieldDecisionInbox.vue';
import P5FieldDecisionDetail from '@/pages/P5FieldDecisionDetail.vue';
import P5HookupReviewInbox from '@/pages/P5HookupReviewInbox.vue';
import P5DemandMatchInbox from '@/pages/P5DemandMatchInbox.vue';
import P5DemandMatchDetail from '@/pages/P5DemandMatchDetail.vue';
import P5ObjectionInbox from '@/pages/P5ObjectionInbox.vue';
import P5ObjectionDetail from '@/pages/P5ObjectionDetail.vue';
// 专题包页面（原 P7ZonesPack / P7ZoneDetail）随专题包整面退出本期（D55/P6）：路由早已下线，
// 零入口孤儿组件已删；后端 topic_package 数据 / handler / repo 保留不动，待立项复活时重建前端面。
import B11ComplianceOps from '@/pages/B11ComplianceOps.vue';
import B13ServiceOps from '@/pages/B13ServiceOps.vue';
import B12IntegrationAdmin from '@/pages/B12IntegrationAdmin.vue';
import B12IamGovernance from '@/pages/B12IamGovernance.vue';
import B12PackageDetail from '@/pages/B12PackageDetail.vue';
import EnginesAdmin from '@/pages/EnginesAdmin.vue';
import PLogin from '@/pages/PLogin.vue';
import PagePlaceholder from '@/pages/PagePlaceholder.vue';

// hash 模式 + 主入口枚举对齐旧 vanilla bundle ROUTES（参见 src/router/route-table.md）。
// F3：P5 六条子路由 + P7 详情已实装；P2/P4/B1.2 部分辅助子路由仍占位。
// 收编：三引擎配置归入 B1.2（/integration-admin/engines），不再作为独立主入口。
const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/workbench' },

  // P1 工作台
  { path: '/workbench', name: 'P1-workbench', component: P1Workbench, meta: { page: 'P1' } },

  // P2 资源发现
  { path: '/discovery', name: 'P2-discovery', component: P2Discovery, meta: { page: 'P2', title: 'P2 资源发现' } },
  { path: '/discovery/catalog-browse', component: P2CatalogBrowse, meta: { page: 'P2', title: 'P2 目录浏览' } },
  { path: '/discovery/resource/:id', component: P2ResourceDetail, meta: { page: 'P2', title: 'P2 资源详情' } },
  { path: '/discovery/catalog/:code', component: P2CatalogDetail, meta: { page: 'P2', title: 'P2 目录详情' } },

  // P3 申请 / 审批 / 跟踪
  // 「办申请」列表页与导航项解体（IA 重构）：列表根重定向到「领数据」（消费方「我的数据」一站式入口，
  // 我的申请 / 我的授权已并入 P4Delivery）；子路由保留为深链目标（详情 / 受理审核 / 异议 / 供需），
  // 角色门见 pageAccess.ts ROUTE_ROLE_OVERRIDES。
  { path: '/request-flow', redirect: '/delivery-exchange' },
  { path: '/request-flow/request/:id', component: P3RequestDetail, meta: { page: 'P3', title: 'P3 申请详情' } },
  { path: '/request-flow/review/:id', component: P3ReviewDetail, meta: { page: 'P3', title: 'P3 审批详情' } },
  { path: '/request-flow/objection', component: P3ObjectionInbox, meta: { page: 'P3', title: 'P3 我的异议' } },
  { path: '/request-flow/objection/new', component: P3ObjectionNew, meta: { page: 'P3', title: 'P3 发起异议' } },
  { path: '/request-flow/objection/:id', component: P3ObjectionDetail, meta: { page: 'P3', title: 'P3 异议详情' } },
  { path: '/request-flow/supply-demand', component: P3SupplyDemand, meta: { page: 'P3', title: 'P3 供需对接' } },

  // P4 交付 / 交换 / 直达
  { path: '/delivery-exchange', name: 'P4-delivery', component: P4Delivery, meta: { page: 'P4', title: 'P4 交付 · 交换 · 直达' } },
  { path: '/delivery-exchange/task/:id', component: P4DeliveryTaskDetail, meta: { page: 'P4', title: 'P4 交付任务详情' } },
  { path: '/delivery-exchange/credential/:id', component: P4Credential, meta: { page: 'P4', title: 'P4 凭据领取' } },

  // P5 提供方管理
  { path: '/provider', name: 'P5-provider', component: P5Provider, meta: { page: 'P5', title: 'P5 提供方管理' } },
  { path: '/provider/national-ext-elem', component: P5NationalExtElem, meta: { page: 'P5', title: 'P5 国家扩展要素编制' } },
  { path: '/provider/wizard/inline-catalog', component: P5InlineCatalogWizard, meta: { page: 'P5', title: 'P5 在线编制目录' } },
  // T9：供数侧目录/资源「管理清单」子路由——由「供数据」概览卡点入，不进 PRODUCT_SHELL_NAV、
  // 不增左导航项（守左导航场景页 ≤10 约束）；activeShellKey('/provider/*')='provider' → 沿用供数 shell 角色门。
  { path: '/provider/catalogs', component: P5CatalogManageList, meta: { page: 'P5', title: 'P5 目录管理清单' } },
  { path: '/provider/resources', component: P5ResourceManageList, meta: { page: 'P5', title: 'P5 资源管理清单' } },
  { path: '/provider/inbox/catalog-review', component: P5CatalogReviewInbox, meta: { page: 'P5', title: 'P5 目录审核收件箱' } },
  { path: '/provider/wizard/reverse-catalog', component: P5ReverseCatalogWizard, meta: { page: 'P5', title: 'P5 反向编目向导' } },
  { path: '/provider/wizard/api-service', component: P5ApiServiceWizard, meta: { page: 'P5', title: 'P5 API 服务化向导' } },
  { path: '/provider/wizard/hookup-submit', component: P5HookupSubmitWizard, meta: { page: 'P5', title: 'P5 资源挂接向导' } },
  { path: '/provider/wizard/quality-rule', component: P5QualityRuleWizard, meta: { page: 'P5', title: 'P5 质量规则向导' } },
  { path: '/provider/inbox/field-decision', component: P5FieldDecisionInbox, meta: { page: 'P5', title: 'P5 反向编目审核收件箱' } },
  { path: '/provider/inbox/field-decision/:id', component: P5FieldDecisionDetail, meta: { page: 'P5', title: 'P5 反向编目审核详情' } },
  { path: '/provider/inbox/hookup-review', component: P5HookupReviewInbox, meta: { page: 'P5', title: 'P5 挂接审核收件箱' } },
  { path: '/provider/inbox/demand-match', component: P5DemandMatchInbox, meta: { page: 'P5', title: 'P5 供需对接收件箱' } },
  { path: '/provider/inbox/demand-match/:id', component: P5DemandMatchDetail, meta: { page: 'P5', title: 'P5 供需对接详情' } },
  { path: '/provider/inbox/objection', component: P5ObjectionInbox, meta: { page: 'P5', title: 'P5 异议响应收件箱' } },
  { path: '/provider/inbox/objection/:id', component: P5ObjectionDetail, meta: { page: 'P5', title: 'P5 异议响应详情' } },

  // P7 共享专区 / 专题包退出本期（D55/P6）：路由下线，组件保留待复活。深链已从 P2/工作台清理。

  // B1.1 合规与运营（后台）——查审计：审计日志 / 证据回放 / 审计事件面（D55/P8·P9，业务运营员 + 安全审计员）。
  { path: '/compliance-ops', name: 'B1.1-compliance', component: B11ComplianceOps, meta: { page: 'B1.1', title: 'B1.1 合规与运营' } },
  // H（D59）：B1.1 异议详情(B11DisputeDetail) 是零入口孤儿页(全站无 link/push/href 指向)，已删；
  // 唯一独占动作「升级督办」(objection.case.escalate) 归位 P5ObjectionDetail 处理方面。

  // B1.3 服务调用监控（后台）——查审计拆分（D55/P8）→ D57⑥ 收窄：网关运行 / 服务调用只读面，
  // 仅平台运维员 + 业务运营员；管理员/审计员退出。与 ops.service.report.query.execute 角色门一致。
  { path: '/service-ops', name: 'B1.3-service-ops', component: B13ServiceOps, meta: { page: 'B1.3', title: '服务调用监控' } },

  // 后台四模块（「接入扩展中心」容器解体，2026-06-05 负责人裁）：外部系统 / 流程与表单配置 / 身份治理
  // 各自独立左导航；路径保留 /integration-admin 前缀（零路由 churn，契约测试不破）。
  { path: '/integration-admin', name: 'B1.2-integration', component: B12IntegrationAdmin, meta: { page: 'B1.2', title: '外部系统' } },
  { path: '/integration-admin/engines', component: EnginesAdmin, meta: { page: 'B1.2', title: '流程与表单配置' } },
  { path: '/integration-admin/iam-governance', component: B12IamGovernance, meta: { page: 'B1.2', title: '身份治理' } },
  { path: '/integration-admin/package/:id', component: B12PackageDetail, meta: { page: 'B1.2', title: '外部系统详情' } },

  // 辅助页
  { path: '/login', component: PLogin, meta: { title: '登录' } },
  { path: '/profile', component: PagePlaceholder, meta: { title: '个人中心' } },
  { path: '/migration-acceptance', component: PagePlaceholder, meta: { title: 'M0 迁移验收（实施工程师）' } },
];

const router = createRouter({
  // base = vite import.meta.env.BASE_URL（/zw-brain/）：hash 模式下 URL 形如 <base>#<route>，
  // 不传 base 会退回 '/'，SPA 跳转后丢掉 /zw-brain/ 段（→ localhost:8800/#/login），
  // 真实 nginx 只路由 /zw-brain/* 时该裸路径会 404。
  history: createWebHashHistory(import.meta.env.BASE_URL),
  routes,
});

router.beforeEach((to) => {
  const role = getProductRole().value;
  if (isRouteAllowedForRole(to.path, role)) return true;
  // 用 to.path 作 fromPath：用户主动想去这个路径，被拦时优先落到
  // 同业务流水线的"对位下一站"（ROUTE_ROLE_OVERRIDES.redirectIfDenied）。
  const fallback = defaultRouteForRole(role, to.path);
  if (to.path === fallback) return true;
  pushToast({ kind: 'warn', title: '无权访问该页面', detail: '已跳转到当前岗位可用入口' });
  return { path: fallback, replace: true };
});

export default router;
