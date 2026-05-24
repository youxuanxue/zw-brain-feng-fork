import { createRouter, createWebHashHistory, type RouteRecordRaw } from 'vue-router';
import P1Workbench from '@/pages/P1Workbench.vue';
import P2Discovery from '@/pages/P2Discovery.vue';
import P2ResourceDetail from '@/pages/P2ResourceDetail.vue';
import P3RequestFlow from '@/pages/P3RequestFlow.vue';
import P3RequestDetail from '@/pages/P3RequestDetail.vue';
import P3ReviewDetail from '@/pages/P3ReviewDetail.vue';
import P4Delivery from '@/pages/P4Delivery.vue';
import P4Credential from '@/pages/P4Credential.vue';
import P5Provider from '@/pages/P5Provider.vue';
import P5FieldDecisionDetail from '@/pages/P5FieldDecisionDetail.vue';
import P7ZonesPack from '@/pages/P7ZonesPack.vue';
import B11ComplianceOps from '@/pages/B11ComplianceOps.vue';
import B11DisputeDetail from '@/pages/B11DisputeDetail.vue';
import B12IntegrationAdmin from '@/pages/B12IntegrationAdmin.vue';
import B13EnginesAdmin from '@/pages/B13EnginesAdmin.vue';
import PagePlaceholder from '@/pages/PagePlaceholder.vue';

// hash 模式 + 8 页面对齐旧 vanilla bundle ROUTES（参见 src/router/route-table.md）。
// F2 阶段：每个主页面接入真实 snapshot 数据骨架（hero + 1-2 panels）；子页（向导 / 详情 / 收件箱
// 详情等）保留 PagePlaceholder，F3 再补业务交互。
const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/workbench' },

  // P1 工作台
  { path: '/workbench', name: 'P1-workbench', component: P1Workbench, meta: { page: 'P1' } },

  // P2 资源发现
  { path: '/discovery', name: 'P2-discovery', component: P2Discovery, meta: { page: 'P2', title: 'P2 资源发现' } },
  { path: '/discovery/catalog-browse', component: PagePlaceholder, meta: { page: 'P2', title: 'P2 目录浏览' } },
  { path: '/discovery/resource/:id', component: P2ResourceDetail, meta: { page: 'P2', title: 'P2 资源详情' } },

  // P3 申请 / 审批 / 跟踪
  { path: '/request-flow', name: 'P3-request-flow', component: P3RequestFlow, meta: { page: 'P3', title: 'P3 申请 · 审批 · 跟踪' } },
  { path: '/request-flow/request/:id', component: P3RequestDetail, meta: { page: 'P3', title: 'P3 申请详情' } },
  { path: '/request-flow/review/:id', component: P3ReviewDetail, meta: { page: 'P3', title: 'P3 审批详情' } },

  // P4 交付 / 交换 / 直达
  { path: '/delivery-exchange', name: 'P4-delivery', component: P4Delivery, meta: { page: 'P4', title: 'P4 交付 · 交换 · 直达' } },
  { path: '/delivery-exchange/task/:id', component: PagePlaceholder, meta: { page: 'P4', title: 'P4 交付任务详情' } },
  { path: '/delivery-exchange/credential/:id', component: P4Credential, meta: { page: 'P4', title: 'P4 凭据领取' } },

  // P5 提供方管理
  { path: '/provider', name: 'P5-provider', component: P5Provider, meta: { page: 'P5', title: 'P5 提供方管理' } },
  { path: '/provider/wizard/reverse-catalog', component: PagePlaceholder, meta: { page: 'P5', title: 'P5 反向编目向导' } },
  { path: '/provider/wizard/api-service', component: PagePlaceholder, meta: { page: 'P5', title: 'P5 API 服务化向导' } },
  { path: '/provider/wizard/quality-rule', component: PagePlaceholder, meta: { page: 'P5', title: 'P5 质量规则向导' } },
  { path: '/provider/inbox/field-decision', component: PagePlaceholder, meta: { page: 'P5', title: 'P5 字段裁决收件箱' } },
  { path: '/provider/inbox/field-decision/:id', component: P5FieldDecisionDetail, meta: { page: 'P5', title: 'P5 字段裁决详情' } },
  { path: '/provider/inbox/hookup-review', component: PagePlaceholder, meta: { page: 'P5', title: 'P5 挂接审核' } },
  { path: '/provider/inbox/demand-match', component: PagePlaceholder, meta: { page: 'P5', title: 'P5 供需对接' } },
  { path: '/provider/inbox/demand-match/:id', component: PagePlaceholder, meta: { page: 'P5', title: 'P5 供需对接详情' } },

  // P7 共享专区 / 专题包
  { path: '/zones-pack', name: 'P7-zones-pack', component: P7ZonesPack, meta: { page: 'P7', title: 'P7 共享专区 · 专题包' } },
  { path: '/zones-pack/zone/:id', component: PagePlaceholder, meta: { page: 'P7', title: 'P7 专题包详情' } },

  // B1.1 合规与运营（后台）
  { path: '/compliance-ops', name: 'B1.1-compliance', component: B11ComplianceOps, meta: { page: 'B1.1', title: 'B1.1 合规与运营' } },
  { path: '/compliance-ops/dispute/:id', component: B11DisputeDetail, meta: { page: 'B1.1', title: 'B1.1 异议详情' } },

  // B1.2 平台接入与扩展中心（后台）
  { path: '/integration-admin', name: 'B1.2-integration', component: B12IntegrationAdmin, meta: { page: 'B1.2', title: 'B1.2 平台接入与扩展中心' } },
  { path: '/integration-admin/iam-governance', component: PagePlaceholder, meta: { page: 'B1.2', title: 'B1.2 身份治理' } },
  { path: '/integration-admin/package/:id', component: PagePlaceholder, meta: { page: 'B1.2', title: 'B1.2 能力包详情' } },

  // B1.3 三引擎配置中心（E3 Wave-2 F7）—— 审批流 / 表单 / 推荐 草稿→预览→入库
  { path: '/engines-admin', name: 'B1.3-engines', component: B13EnginesAdmin, meta: { page: 'B1.3', title: 'B1.3 三引擎配置中心' } },

  // 辅助页
  { path: '/login', component: PagePlaceholder, meta: { title: '登录中转' } },
  { path: '/profile', component: PagePlaceholder, meta: { title: '个人中心' } },
  { path: '/migration-acceptance', component: PagePlaceholder, meta: { title: 'M0 迁移验收（实施工程师）' } },
];

const router = createRouter({
  history: createWebHashHistory(),
  routes,
});

export default router;
