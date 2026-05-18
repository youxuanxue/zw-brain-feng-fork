# preflight-debt

Outstanding items intentionally deferred from the current preflight gate set. Each entry must list
the symptom, the deferred decision, and the trigger that forces a re-evaluation.

## 2026-05-18 — BFF session store is single-process in-memory

- **Where**: `zw_brain/shared/auth_session.AuthSessionStore` (thread-safe dict in the REST entry process).
- **Implication**: A multi-process / multi-replica REST deployment will hand out cookies that only
  resolve on the issuing replica. Subsequent requests routed to a different replica look like
  un-authenticated traffic.
- **Why deferred**: Current zw-brain REST deployment is single-process (one `zw-brain-rest` worker
  per node, sticky LB upstream). Adding Redis / DB-backed sessions before any deployment actually
  needs it would be premature infra.
- **Trigger to re-evaluate**: First time we want to run `zw-brain-rest` behind a non-sticky load
  balancer, or run more than one REST worker, switch to an out-of-process backend (Redis preferred:
  TTL + `secrets.compare_digest` semantics already match the in-memory store).
- **No mechanical preflight check**: Adding a "deployment topology" gate today would be noise. The
  trigger above is concrete enough that we'll know when to act.
