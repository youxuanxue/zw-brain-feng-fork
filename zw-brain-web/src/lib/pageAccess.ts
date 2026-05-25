/**
 * 页面访问 SoT：与 config/productShellNav.ts 的 shell key / roles 对齐。
 * 后端快照裁剪见 zw_brain/domain/web_snapshot_redaction.py（须同步改 roles 集合）。
 */

import {
  activeShellKey,
  PRODUCT_SHELL_NAV,
  visibleShellNav,
  type ShellNavItem,
} from '@/config/productShellNav';

/** 不参与 shell 权限判定的辅助路由（登录 / 个人中心等）。 */
const PUBLIC_ROUTE_PREFIXES = ['/login', '/profile', '/migration-acceptance'] as const;

export function shellItemForKey(key: string): ShellNavItem | undefined {
  return PRODUCT_SHELL_NAV.find((item) => item.key === key);
}

export function isRouteAllowedForRole(path: string, role: string): boolean {
  const normalized = path.startsWith('/') ? path : `/${path}`;
  if (normalized === '/' || PUBLIC_ROUTE_PREFIXES.some((p) => normalized.startsWith(p))) {
    return true;
  }
  const key = activeShellKey(normalized);
  const item = shellItemForKey(key);
  if (!item) return true;
  return item.roles.includes(role);
}

/** 当前岗位无权访问时，跳到该岗位可见的第一个主导航页。 */
export function defaultRouteForRole(role: string): string {
  const nav = visibleShellNav(role);
  return nav[0]?.to ?? '/workbench';
}
