"""Background workers — drain queue topics and durable outbox records.

Whitelisted for direct `await blockchain_adapter.anchor(...)` per
`scripts/check_blockchain_async.py` whitelist (this is the right side of the
queue boundary).
"""
from __future__ import annotations

from zw_brain.shared import queue as _queue
from zw_brain.shared.database_store import DatabaseStore
from zw_brain.skills.blockchain_adapter import anchor as _anchor


async def run_once() -> int:
    jobs = await _queue.drain()
    processed = 0
    store = DatabaseStore()
    seen_hashes: set[str] = set()

    for job in jobs:
        if job.topic != "blockchain.anchor":
            continue
        content_hash = job.payload["content_hash"]
        await _anchor(content_hash, chain_id=job.payload.get("chain_id", "mock-chain"))
        store.mark_anchor_delivered(content_hash)
        seen_hashes.add(content_hash)
        processed += 1

    for record in store.list_pending_anchor_outbox():
        if record.content_hash in seen_hashes:
            continue
        await _anchor(record.content_hash, chain_id=record.chain_id)
        store.mark_anchor_delivered(record.content_hash)
        processed += 1

    return processed
