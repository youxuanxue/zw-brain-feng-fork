"""zw-brain — AI-native re-architecture of the legacy 一体化大数据平台.

The active implementation baseline follows:
- `docs/approved/zw-brain-architecture-v4-gpt55.md` (+ 附录 D, D23-D29)
- `docs/approved/zw-brain-data-model-v4-gpt55.md`
- `docs/approved/zw-brain-roles-v2.md` (7 角色规范，D23 retrofit)
- `docs/approved/zw-brain-information-architecture-v2.md` (3 旅程 IA，D24 retrofit)
- `docs/approved/zw-brain-gate1.1-retrofit-2026-05-19.md` (GATE-1.1 评审主文档)

Current implementation includes real runtime entry surfaces, canonical skill
registration, database-backed aggregate projection, synchronous audit + async
anchor outbox, a main WebUI, and a separate read-only K12 dashboard unit.
"""

__version__ = "1.0.0"
