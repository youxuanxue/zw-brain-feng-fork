"""Blockchain anchor adapter (whitelisted for direct await).

This module is the **only** place in the codebase allowed to `await
blockchain.anchor(...)` synchronously, because workers under
`zw_brain.background_tasks/` invoke it after dequeuing from the
`blockchain.anchor` topic. Business-path Skills MUST NOT import this module
directly — they enqueue via `zw_brain.shared.queue.enqueue`.

Per D5: the adapter is a thin pluggable shim. Once the external chain
protocol is finalized, only the `_call_chain` private helper changes; the
public `anchor(...)` signature is frozen.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class AnchorReceipt:
    tx_hash: str
    block_height: int | None
    chain_id: str
    confirmed_at: datetime


async def anchor(content_hash: str, *, chain_id: str = "mock-chain") -> AnchorReceipt:
    """Anchor `content_hash` to the configured chain.

    The current local adapter returns a deterministic receipt without
    performing external I/O. Failure of the real chain integration MUST raise
    — workers handle retry + alert; the business path is already insulated by
    the queue.
    """
    return AnchorReceipt(
        tx_hash=f"mock:{content_hash[:16]}",
        block_height=None,
        chain_id=chain_id,
        confirmed_at=datetime.now(UTC),
    )
