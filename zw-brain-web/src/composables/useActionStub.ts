import { ref } from 'vue';
import { authFetch } from './useAuth';
import { loadSnapshot } from './useSnapshot';

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
}

let _idSeq = 1;
export const toasts = ref<ToastEntry[]>([]);

export function pushToast(entry: Omit<ToastEntry, 'id'>): number {
  const id = _idSeq++;
  toasts.value.push({ id, ...entry });
  if (entry.ttl !== 0) {
    const ms = entry.ttl ?? 4500;
    window.setTimeout(() => dismissToast(id), ms);
  }
  return id;
}

export function dismissToast(id: number): void {
  toasts.value = toasts.value.filter((t) => t.id !== id);
}

export interface ActionStubOptions {
  skillId: string;
  payload?: Record<string, unknown>;
  successTitle?: string;
  pendingBackend?: string; // e.g. "E2 申请管理 handler"
  refreshSnapshotAfter?: boolean;
  role?: string;
}

// Sticky confirmation default — see policy.py:386 (human_confirmation_required runtime gate).
// Clicking a page button IS the user's explicit confirmation; without this default, 130 write
// skills with `human_confirmation_required: true` would be silently rejected by the policy gate.
// Future: if a flow needs an additional modal step (e.g. irreversible destructive ops), the
// caller should pass `{ confirmed: false }` and present its own confirm UI before re-invoke.
export async function invokeActionStub(opts: ActionStubOptions): Promise<{ ok: boolean; status: number; data?: unknown }> {
  const role = opts.role ?? 'ROLE_ORGAN_OPERATER';
  try {
    const resp = await authFetch(`/api/skills/${opts.skillId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ role, confirmed: true, ...(opts.payload ?? {}) }),
    });
    if (resp.ok) {
      const data = await resp.json().catch(() => undefined);
      pushToast({ kind: 'ok', title: opts.successTitle ?? '已提交', detail: opts.skillId });
      if (opts.refreshSnapshotAfter !== false) {
        void loadSnapshot(role);
      }
      return { ok: true, status: resp.status, data };
    }
    const detail =
      resp.status === 404 || resp.status === 405 || resp.status === 501
        ? `${opts.pendingBackend ? `等 ${opts.pendingBackend} land` : '后端尚未实现'} · ${opts.skillId}`
        : `${opts.skillId} 返回 HTTP ${resp.status}`;
    pushToast({ kind: 'warn', title: '操作待后端 land', detail });
    return { ok: false, status: resp.status };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    pushToast({ kind: 'error', title: '调用失败', detail: `${opts.skillId} · ${msg}` });
    return { ok: false, status: 0 };
  }
}
