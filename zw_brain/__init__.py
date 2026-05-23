"""zw-brain — AI-native re-architecture of the legacy 一体化大数据平台.

The active implementation baseline follows:
- `docs/approved/zw-brain-architecture.md` (+ 附录 D, D23-D29)
- `docs/approved/zw-brain-data-model.md`
- `docs/approved/zw-brain-roles.md` (7 角色规范，D23 retrofit)
- `docs/approved/zw-brain-architecture.md` (3 旅程 IA，D24 retrofit)
- `docs/approved/zw-brain-architecture.md` (GATE-1.1 评审主文档)

Current implementation includes real runtime entry surfaces, canonical skill
registration, database-backed aggregate projection, synchronous audit + async
anchor outbox, and a main WebUI. K12 dashboard unit retired (详见 D15 二次反转).
"""

__version__ = "1.0.0"
