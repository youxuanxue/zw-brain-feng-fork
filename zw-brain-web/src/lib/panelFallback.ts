/**
 * 面板加载失败回退收口（R-007）。
 *
 * 政务查审计 / 合规 / 接入面板的 composable 在 API 失败时此前一律回填本地
 * fixtures/*.ts 的捏造切片 + source='fixture'（UI 渲染「演示数据」徽标）。问题：
 * **生产**环境后端真故障时，会向用户展示一条假的审计事件链 / 假网关状态 / 假候选记录，
 * 违 D11（业务数据禁 Mock）/ D47（凭据诚实化）方向——政务审计页尤其不能在故障时编数据。
 *
 * 收口（单点，8 处复用、不复制判断）：
 *   - 开发构建（import.meta.env.DEV）：保留 fixture 回退，方便后端未起时本地走查；
 *     source='fixture' → 徽标「演示数据」诚实标识。
 *   - 生产构建：**绝不**渲染 fixture。data 置空（null / 空切片），source='error'
 *     → DataSourceBadge 渲染「不可用」，页面 v-else 空态如实呈现「数据暂不可用」，
 *     不编造任何业务数据。
 *
 * 新增带 fixture 回退的面板 composable 一律调本 helper，禁止在 composable 内
 * 自己写 `import.meta.env.DEV` 分支（避免 8 份判断漂移）。
 */
import type { Ref } from 'vue';

/** 是否允许 fixture 回退：仅开发构建。生产构建 fixture 一律不上屏。 */
export function fixtureFallbackAllowed(): boolean {
  return Boolean(import.meta.env.DEV);
}

/**
 * 在 catch 分支统一决定回退形态。
 *
 * @param refs.data       面板数据 ref（失败时写入）
 * @param refs.source     面板来源 ref（写 'fixture' 或 'error'）
 * @param fixture         开发构建下回退展示的本地切片
 * @param emptyValue      生产构建下的诚实空值（null / 空数组 / 空 summary 等），
 *                        必须与该面板「无数据」语义一致，使页面渲染空态而非假数据
 */
export function applyPanelFallback<T, S extends string>(
  refs: { data: Ref<T>; source: Ref<S> },
  fixture: T,
  emptyValue: T,
): void {
  if (fixtureFallbackAllowed()) {
    refs.data.value = fixture;
    refs.source.value = 'fixture' as S;
  } else {
    refs.data.value = emptyValue;
    refs.source.value = 'error' as S;
  }
}
