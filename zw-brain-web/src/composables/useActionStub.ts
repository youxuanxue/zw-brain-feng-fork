import { ref } from 'vue';
import { authFetch } from './useAuth';
import { loadSnapshot, invalidateSnapshot } from './useSnapshot';
import { invalidateWorkbench } from './useWorkbench';
import { getProductRole } from './useProductRole';
import { apiUrl } from './useApiBase';

// F3 业务交互 stub：把 7 主页面 + 6 子页的 onClick 收口到此处。
// 真正 land 的业务 handler（E1/E2/E4 输出）通过 /api/skills/<skill_id> 调到；
// 未 land 的会返 404/405/501，我们把它转成结构化 toast「该能力等 X 后端 land」
// 而不是炸红错。Worker 这一层不假装事先知道哪些 skill 已 land。

export type ToastKind = 'info' | 'ok' | 'warn' | 'error';

export interface ToastEntry {
  id: number;
  kind: ToastKind;
  title: string;
  detail?: string;
  ttl?: number;
  channel?: string;
  key?: string;
}

let _idSeq = 1;
export const toasts = ref<ToastEntry[]>([]);
const _toastTimers = new Map<number, number>();
const MAX_TOASTS = 3;

export function pushToast(entry: Omit<ToastEntry, 'id'>): number {
  const normalized = normalizeToastEntry(entry);
  const existing = normalized.channel && normalized.key
    ? toasts.value.find((t) => t.channel === normalized.channel && t.key === normalized.key)
    : undefined;
  if (existing) {
    toasts.value = toasts.value.map((t) => (
      t.id === existing.id ? { ...t, ...normalized, id: t.id } : t
    ));
    scheduleToastDismiss(existing.id, normalized.ttl);
    return existing.id;
  }

  const id = _idSeq++;
  toasts.value = [...toasts.value, { id, ...normalized }];
  while (toasts.value.length > MAX_TOASTS) {
    dismissToast(toasts.value[0].id);
  }
  scheduleToastDismiss(id, normalized.ttl);
  return id;
}

export function dismissToast(id: number): void {
  const timer = _toastTimers.get(id);
  if (timer !== undefined) {
    window.clearTimeout(timer);
    _toastTimers.delete(id);
  }
  toasts.value = toasts.value.filter((t) => t.id !== id);
}

function normalizeToastEntry(entry: Omit<ToastEntry, 'id'>): Omit<ToastEntry, 'id'> {
  if (entry.channel || entry.key) return entry;
  if (['已切换岗位', '岗位已自动调整', '无权访问该页面'].includes(entry.title)) {
    return { ...entry, channel: 'access', key: 'role-route' };
  }
  return entry;
}

function scheduleToastDismiss(id: number, ttl?: number): void {
  const previous = _toastTimers.get(id);
  if (previous !== undefined) window.clearTimeout(previous);
  _toastTimers.delete(id);
  if (ttl === 0) return;
  const ms = ttl ?? 4500;
  _toastTimers.set(id, window.setTimeout(() => dismissToast(id), ms));
}

export interface ActionStubOptions {
  skillId: string;
  payload?: Record<string, unknown>;
  successTitle?: string;
  pendingBackend?: string; // e.g. "E2 申请管理 handler"
  refreshSnapshotAfter?: boolean;
  role?: string;
  suppressSuccessToast?: boolean;
}

// Sticky confirmation default — see policy.py:386 (human_confirmation_required runtime gate).
// Clicking a page button IS the user's explicit confirmation; without this default, 130 write
// skills with `human_confirmation_required: true` would be silently rejected by the policy gate.
// Future: if a flow needs an additional modal step (e.g. irreversible destructive ops), the
// caller should pass `{ confirmed: false }` and present its own confirm UI before re-invoke.
export async function invokeActionStub(opts: ActionStubOptions): Promise<{ ok: boolean; status: number; data?: unknown }> {
  const role = opts.role ?? getProductRole().value;
  try {
    const resp = await authFetch(apiUrl(`/api/skills/${opts.skillId}`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ role, confirmed: true, ...(opts.payload ?? {}) }),
    });
    if (resp.ok) {
      const data = await resp.json().catch(() => undefined);
      if (!opts.suppressSuccessToast) {
        pushToast({ kind: 'ok', title: opts.successTitle ?? '已提交' });
      }
      if (opts.refreshSnapshotAfter !== false) {
        // FU-3 写后失效：写能力改了真实库积压，作废该 role 的快照 + 工作台缓存再拉新——
        //   工作台待办（workbench_backlog_projection 现算）不再停在写前的陈旧值。
        invalidateSnapshot(role);
        invalidateWorkbench(role);
        void loadSnapshot(role);
      }
      return { ok: true, status: resp.status, data };
    }
    const data = await resp.json().catch(() => undefined);
    const pendingBackend = resp.status === 404 || resp.status === 405 || resp.status === 501;
    if (pendingBackend) {
      pushToast({
        kind: 'warn',
        title: '暂不可用',
        detail: '该操作尚未在本环境开通，请稍后再试或联系平台管理员。',
      });
    } else {
      const bodyDetail =
        data && typeof data === 'object' && 'detail' in (data as object)
          ? String((data as Record<string, unknown>).detail ?? '')
          : '';
      // 后端人话 detail 优先透传（不被通用文案覆盖）。后端 AccessDeniedError 是两义的：
      // 既可能是真权限失败，也可能是业务校验（如挂接归属与目录不一致）伪装成 403——把
      // detail 当作纯权限问题改写会把「你填错/没填归属」误译成「岗位无权」（误导）。
      // 故：detail 非空就回显它；只有 detail 为空（后端没给人话）才按状态码回落通用文案。
      let detail: string;
      const missing = bodyDetail.match(/missing required input field\(s\):\s*(.+?)\s*\(skill:/i);
      if (missing) {
        detail = `缺少必填信息：${missing[1]}。请重新选择目录或联系管理员补全 schema 引用。`;
      } else if (bodyDetail.includes('self_approval_not_allowed')) {
        detail = '申请提交人本人不能审批自己的申请，请由其他有权限的部门管理员办理。';
      } else if (bodyDetail.includes('approval_direction_mismatch')) {
        detail = '当前部门不是该资源的提供方部门，不能办理此申请审批。';
      } else if (bodyDetail) {
        detail = bodyDetail;
      } else if (resp.status === 403) {
        detail = '当前岗位无权执行此操作，请切换岗位或联系管理员。';
      } else {
        detail = '请检查当前岗位权限或稍后重试。';
      }
      pushToast({ kind: 'info', title: '操作未完成', detail });
    }
    return { ok: false, status: resp.status, data };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    pushToast({ kind: 'error', title: '调用失败', detail: msg });
    return { ok: false, status: 0 };
  }
}
