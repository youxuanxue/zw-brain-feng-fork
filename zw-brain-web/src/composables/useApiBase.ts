// 反向代理部署前缀的单一事实源。值由 vite `base` 注入（见 vite.config.ts，形如 '/zw-brain/'），
// 与后端 zw_brain/entry/rest/server.py::APP_PATH_PREFIX 对齐。所有前端请求路径与登录回跳都从这里派生，
// 禁止再各处硬编码 '/zw-brain/' 字面量——改前缀只动 vite base 一处。
const BASE = import.meta.env.BASE_URL;

/** 把后端路径（以 / 开头，如 /api/skills/x、/auth/iaf/token、/health）映射到带部署前缀的绝对路径。 */
export function apiUrl(path: string): string {
  return BASE.replace(/\/$/, '') + path;
}

/** 登录/登出回跳到的同源应用根，形如 https://host/zw-brain/。 */
export function appOrigin(): string {
  return `${window.location.origin}${BASE}`;
}
