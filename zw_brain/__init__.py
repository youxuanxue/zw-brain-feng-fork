"""zw-brain — AI-native re-architecture of the legacy 一体化大数据平台.

The active implementation baseline follows:
- `docs/approved/zw-brain-architecture-v4-gpt55.md`
- `docs/approved/zw-brain-data-model-v4-gpt55.md`
- `docs/approved/zw-brain-golden-path-r1-r3-r5-v1.md`
- `docs/approved/zw-brain-user-roles-and-journeys-v1.md`

Current implementation includes real runtime entry surfaces, canonical skill
registration, database-backed aggregate projection, synchronous audit + async
anchor outbox, a main WebUI, and a separate read-only K12 dashboard unit.
"""

__version__ = "1.0.0"
