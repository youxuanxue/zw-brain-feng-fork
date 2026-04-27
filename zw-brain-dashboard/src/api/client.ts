/**
 * dashboard read-only HTTP client.
 *
 * Per design baseline D15: this client may issue **GET only**. Any attempt to
 * add `axios.post` / `fetch(..., { method: 'POST' })` / similar mutation
 * helpers here is mechanically blocked by `scripts/check_dashboard_readonly.py`
 * (preflight section 11).
 *
 * Current implementation uses the global `fetch` API to keep the read-only
 * dashboard dependency-free; framework choice may still evolve without
 * changing the GET-only boundary here.
 */

export interface DashboardQueryOptions {
  /** ISO 8601 cutoff for time-windowed queries; defaults to now. */
  asOf?: string;
  /** Optional bearer token; supplied by parent SPA after login. */
  bearer?: string;
  /** Abort signal for request cancellation in component lifecycle. */
  signal?: AbortSignal;
}

const DEFAULT_BASE = "/api";

function buildHeaders(bearer?: string): HeadersInit {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (bearer) {
    headers["Authorization"] = `Bearer ${bearer}`;
  }
  return headers;
}

/**
 * Read a `dashboard.*` Skill result. The verb prefix `query` (read-only) is
 * enforced by convention; `dashboard.render_*`, `dashboard.list_*`, and
 * `dashboard.summary_*` are all acceptable.
 */
export async function queryDashboardSkill<T>(
  skillId: string,
  params: Record<string, unknown> = {},
  options: DashboardQueryOptions = {},
): Promise<T> {
  if (!skillId.startsWith("dashboard.")) {
    throw new Error(
      `dashboard client refuses non-dashboard skill_id: ${skillId} (D15: read-only consumer of dashboard.* only)`,
    );
  }
  const url = new URL(`${DEFAULT_BASE}/skills/${skillId}`, window.location.origin);
  for (const [k, v] of Object.entries({ asOf: options.asOf, ...params })) {
    if (v !== undefined && v !== null) {
      url.searchParams.set(k, String(v));
    }
  }
  const resp = await fetch(url.toString(), {
    method: "GET",
    headers: buildHeaders(options.bearer),
    signal: options.signal,
  });
  if (!resp.ok) {
    throw new Error(`dashboard skill ${skillId} failed: HTTP ${resp.status}`);
  }
  return (await resp.json()) as T;
}
