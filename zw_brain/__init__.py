"""zw-brain — AI-native re-architecture of the legacy 一体化大数据平台.

Phase 0 placeholder package. The real layout follows
docs/approved/zw-brain-architecture.md §4.4.5:

    entry/                 — L1.2 REST / L1.3 MCP / L1.4 A2A boundaries
    agents/                — orchestrating agents (planner, executor, reviewer)
    orchestrator/          — LangGraph / equivalent state machine wiring
    skills/                — atomic capabilities (the canonical contract per D2)
    skill_registration/    — registry adapter + manifest cache
    shared/inference/      — Group Inference Platform SDK gateway (D6 / D14)
    shared/audit/          — synchronous audit bus (D4 upper half)
    shared/queue/          — async dispatch queue for blockchain anchor (D4 lower half)
    background_tasks/      — workers that drain shared/queue
    adapters/              — one-way sync from legacy data-governance / external systems (D7)

All modules are currently empty stubs to satisfy preflight scanners; real
implementation lands per Phase-1+ user stories.
"""

__version__ = "0.0.0"
