#!/usr/bin/env python3
"""防回潮守卫：全盘 PostgreSQL 后，活跃代码禁出现 SQLite 残留。

承 §5 升级原则——zw-brain 已彻底移除 SQLite（全 PG 迁移）。db.py 在运行时对
``ZW_BRAIN_DB_PATH`` / ``sqlite://`` URL fail-closed raise；本守卫在提交期把同一目标
硬化到**静态层**：扫描受 git 跟踪的代码（.py/.sh/.yml/.yaml/.toml），任何 ``sqlite`` /
``ZW_BRAIN_DB_PATH`` / ``SHADOW_DB`` / ``SEED_DB`` 命中即 FAIL，防止有人再把 SQLite 旋钮
悄悄写回来（运行时被 conftest 克隆/db.py 忽略而静默存活）。

豁免：
  - 故意提及（fail-closed 守卫本体、退役说明）须在该行加 ``# sqlite-allow: <理由>``。
  - 历史决策/重构文档（docs/ 下，非代码）不在扫描范围。
不扫 .md——历史文档对 SQLite 的叙述是既成事实，单列文档清理，不进本机械门。
"""
from __future__ import annotations

import re
import subprocess

# 目标是 SQLite 的**实际使用/旋钮设置**，不是注释里「已不再 sqlite」之类的叙述提及，
# 否则迁移说明文字会全员误报。逐条针对真正的复活向量：
FORBIDDEN_PATTERNS = [
    r"import\s+sqlite3",                                    # 原生 sqlite3 模块
    r"\bsqlite3\s*\.",                                      # sqlite3.connect 等
    r"sqlite:/",                                            # sqlite:// URL 字面量
    r'\benviron\[\s*["\']ZW_BRAIN_DB_PATH["\']\s*\]\s*=',   # os.environ["…"] = 赋值
    r'\benv\[\s*["\']ZW_BRAIN_DB_PATH["\']\s*\]\s*=',       # env["…"] = （subprocess env）
    r'setenv\(\s*["\']ZW_BRAIN_DB_PATH',                    # monkeypatch.setenv("…")
    r'^\s*(ENV\s+)?ZW_BRAIN_DB_PATH\s*=',                   # shell export / Dockerfile ENV
    r'shutil\.copy\w*\([^)]*\.db\b',                        # 拷贝 sqlite .db 文件（shadow 范式）
]
FORBIDDEN = re.compile("|".join(FORBIDDEN_PATTERNS))
SCAN_DIRS = ["zw_brain", "scripts", "tests", "alembic", ".github"]
SCAN_EXT = (".py", ".sh", ".yml", ".yaml", ".toml")
ALLOW_FILE_SUBSTR = (
    "scripts/check_no_sqlite.py",
    # db.py 是 fail-closed 守卫本体——它命名 SQLite 正是为了在运行时 raise 拒绝它：
    "zw_brain/shared/db.py",
    # 迁移范式文档（描述「旧 SQLite 写法 → 新 PG 写法」，故意保留旧 token 作对照）：
    "tests/_pg_realistic.py",
    "tests/_seed_guard.py",
)
ALLOW_LINE_MARKER = "# sqlite-allow:"


def main() -> int:
    tracked = subprocess.run(
        ["git", "ls-files", *SCAN_DIRS], capture_output=True, text=True, check=False
    ).stdout.split()
    hits: list[str] = []
    for path in tracked:
        if not path.endswith(SCAN_EXT):
            continue
        if any(sub in path for sub in ALLOW_FILE_SUBSTR):
            continue
        try:
            lines = open(path, encoding="utf-8").read().splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for n, line in enumerate(lines, 1):
            if FORBIDDEN.search(line) and ALLOW_LINE_MARKER not in line:
                hits.append(f"{path}:{n}: {line.strip()[:110]}")
    if hits:
        print(f"[no-sqlite] FAIL: {len(hits)} 处 SQLite 残留（全盘 PG 后禁；故意提及加 `# sqlite-allow: <理由>`）：")
        for h in hits[:50]:
            print("  " + h)
        if len(hits) > 50:
            print(f"  …… 另 {len(hits) - 50} 处")
        return 1
    print(f"[no-sqlite] OK: 扫描 {len(tracked)} 个受跟踪代码文件，无 SQLite 残留")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
