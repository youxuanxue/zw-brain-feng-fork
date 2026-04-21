"""Background workers — drain `zw_brain.shared.queue` topics.

Whitelisted for direct `await blockchain_adapter.anchor(...)` per
`scripts/check_blockchain_async.py` whitelist (this is the right side of the
queue boundary).

Phase-0 ships only a placeholder dispatcher; real worker implementations
arrive with Phase 1.
"""
from __future__ import annotations

from zw_brain.shared import queue as _queue
from zw_brain.skills.blockchain_adapter import anchor as _anchor


async def run_once() -> int:
    """Drain the queue once, dispatch each job to its handler, return the
    count of processed jobs. Tests use this to assert end-to-end behavior
    without spinning a long-lived worker.
    """
    jobs = await _queue.drain()
    processed = 0
    for job in jobs:
        if job.topic == "blockchain.anchor":
            await _anchor(job.payload["content_hash"], chain_id=job.payload.get("chain_id", "mock-chain"))
            processed += 1
        # Other topics added in Phase 1 (notification.send, national.relay_submit, ...).
    return processed
