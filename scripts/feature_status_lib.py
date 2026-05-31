#!/usr/bin/env python3
"""feature_status_lib.py — 状态函数唯一实现（status 不存储，每次现算）.

全局宪法 §5 + 单一事实源：feature 的完成状态不是被存的事实，是三个不可再分
原料的纯函数，由生成器 / 守卫共同 import，绝不手敲、绝不存第二份。

    STATUS(f) = f( SPEC(f), MEASUREMENT(f), SIGN-OFF(f) )

三原料（各单一写入者）
----------------------
  SPEC       = `.feature`（场景 + `# Owner/# Pytest/# Twin-F` 链接边 + 可选 `# Deferred:`）
  MEASUREMENT= `.testing/status/measurement/<sha>.json`（机器实跑 pytest 产出，带 git_sha）
  SIGN-OFF   = `.testing/signoff/<scope>.signoff.yaml` 账本的 `covers`（唯一权威源、来源无关、
               独立于 twin；append-only 人类判断；D46.b）

判定（词表 .testing/README.md:72 — Draft|Ready|InTest|Done；+ Backlog=排期外）
  signed ∧ green        -> Done     # 真绿 ∧ 业务签字（最诚实：工程完成 ∧ 业务验收）
  signed ∧ ¬green       -> Ready    # R13：签字可先于实现（README:137）
  ¬signed ∧ (green ∨ 有测试) -> InTest  # 在测/已绿但未签字（代码完成待签字）
  else                  -> Draft    # 纯意图
  `# Deferred:` 存在      -> Backlog  # 不可派生的排期外意图，单列、不进 4 值阶梯

green(f) 只信 committed 测量产物里 result==pass **且内容指纹仍匹配当前文件**（fail-closed）；
信任锚是**被测内容指纹**（`.feature` + 引用测试文件哈希），不是 git_sha——squash-merge
改写历史但不动文件内容 → 指纹不变 → 不孤儿；测试/规格真变了 → 指纹失配 → 自动非绿（D46.g）。
绝不读 plan.yaml 的 `status:`（决策 a：那是 supervisor 执行态，且会重蹈 F13 谎报）。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_trace_triangle import (  # noqa: E402
    PYTEST_PATH_RE,
    REPO,
    TESTING_DIR,
    _parse_feature_header,
)

MEASUREMENT_DIR = REPO / ".testing" / "status" / "measurement"
LADDER = ("Draft", "InTest", "Ready", "Done")  # 排序用；Backlog 单列


def all_features() -> list[Path]:
    return sorted(TESTING_DIR.rglob("*.feature"))


def feature_rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def feature_wave(path: Path) -> str:
    """从目录 .testing/waves/wave-N-.../ 推 Wave；非 wave 目录（cross-cutting）→ 'cross'。"""
    for part in path.parts:
        if part.startswith("wave-"):
            return part
    return "cross"


def _deferred_reason(path: Path) -> str | None:
    """读 `# Deferred:` header（spec 自有的排期外标记，替代被删的 `# Status: Backlog`）。"""
    try:
        with path.open(encoding="utf-8") as fh:
            for i, line in enumerate(fh):
                if i > 30:
                    break
                if line.startswith("# Deferred:"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        return None
    return None


def test_refs(pytest_val: str | None) -> list[str]:
    """# Pytest 里的真实测试路径（pending/空 → []）。

    test-runner 无关：既含 pytest 模块（tests/**.py），也含 Playwright e2e（tests/**.spec.ts）。
    webui 类 feature 只有 e2e、pytest 轴看不到，故必须把 spec 也算作测试 ref，否则它们永远
    refs=0 → green 永 False → 即便签字也卡死 Ready（D46 e2e 测量盲区修复）。
    """
    if not pytest_val or pytest_val == "pending":
        return []
    out: list[str] = []
    for m in PYTEST_PATH_RE.finditer(pytest_val):
        out.append(m.group(1))
    return out


def feature_fingerprint(path: Path) -> str:
    """内容指纹 = sha256(`.feature` 规格 + 其引用的每个测试文件内容)。

    信任锚（D46.g）：与 git 历史无关 → **squash-merge 免疫**（squash 改写历史不动文件内容，
    指纹不变）；测试或规格**真的变了**才变（→ green() 自动失效，逼重采）。缺失的测试文件也计入
    （→ 指纹变 → 非绿），所以删测试不会悄悄留住旧 pass。refs 排序后入哈希，结果确定、与克隆深度无关。
    """
    h = hashlib.sha256()
    try:
        h.update(path.read_bytes())
    except OSError:
        h.update(b"<missing-feature-spec>")
    _, pytest_val, _ = _parse_feature_header(path)
    for ref in sorted(test_refs(pytest_val)):
        h.update(b"\x00" + ref.encode("utf-8") + b"\x00")
        try:
            h.update((REPO / ref).read_bytes())
        except OSError:
            h.update(b"<missing-test-file>")
    return h.hexdigest()


def load_measurement() -> dict | None:
    """选 captured_at 最新的 committed 测量产物；无则 None。

    返回 {"git_sha":..., "captured_at":..., "features": {rel: {result, ...}}}。

    **环境无关现算（CI 假红修复）**：committed 进本分支树的产物即是真相，无条件信任，
    不再按 git_sha 做祖先/对象存在过滤。曾用 `merge-base --is-ancestor` 再改 `cat-file -e`，
    两者都依赖该 commit 对象在 clone 中可达——CI 矩阵多数 job 用 `fetch-depth: 1` 浅克隆，
    产物 git_sha 指向的父 commit 不在 clone 里 → 过滤掉产物 → green 全 False → gen --check
    在 CI 与本地字节漂移（假红）。产物是仓内 committed 文件，被 checkout 出来即属本分支事实，
    内容现算不该依赖 git 历史形状。「陈旧/异线」健康度判定全部交给 preflight 段 60（独立
    merge-base，仅 WARN，非阻断），不渗进内容现算。fail-closed 仍成立：无产物 → None → 非绿。
    """
    if not MEASUREMENT_DIR.is_dir():
        return None
    best: dict | None = None
    for fp in MEASUREMENT_DIR.glob("*.json"):
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if best is None or d.get("captured_at", "") > best.get("captured_at", ""):
            best = d
    return best


SIGNOFF_DIR = REPO / ".testing" / "signoff"


def load_signoff_features() -> set[str]:
    """已业务签字的 feature 路径集 = `.testing/signoff/*.signoff.yaml` 各账本的 `covers` 并集。

    SIGN-OFF 唯一权威源（D46）：append-only 签字账本，独立于 twin（来源无关——twin 规划内、
    其他会话直签合并 main、纯人工验收的功能统一往这里追加）。不再借 twin 的 spec_ref（那是
    执行字段，曾把 j1-supply-demand 误标、把 b1-2-trust-level 漏标）。decision_only 账本
    covers 留空、不抬 feature 状态（纯记决策史）。
    """
    signed: set[str] = set()
    if not SIGNOFF_DIR.is_dir():
        return signed
    for fp in SIGNOFF_DIR.glob("*.signoff.yaml"):
        try:
            d = yaml.safe_load(fp.read_text(encoding="utf-8")) or {}
        except (yaml.YAMLError, OSError):
            continue
        for ref in d.get("covers") or []:
            if str(ref).strip().endswith(".feature"):
                signed.add(str(ref).strip())
    return signed


def green(rel: str, refs: list[str], measurement: dict | None,
          fingerprint: str | None = None) -> bool:
    """测量轴（test-runner 无关）：该 feature 的测试（pytest 或 e2e）被实跑且 result==pass，
    **且测量记录的内容指纹仍匹配当前文件**（D46.g 新鲜度门）。

    capture_feature_status.py 把 .py（pytest 退出码）与 .spec.ts（Playwright 退出码）统一回填进
    同一测量产物的 features[rel].result；green() 只读这一个聚合结果，不关心用哪个 runner。
    e2e 未跑（e2e-not-run）的 feature result≠pass，fail-closed 不算绿。

    指纹门（fail-closed）：传入 `fingerprint`（当前 feature_fingerprint）时，测量记录里存的
    `fingerprint` 必须逐字相等才算绿——记录无指纹（旧格式/孤儿产物）或测试/规格已变 → 非绿，
    逼重采。不传 fingerprint（历史调用）时退化为只看 result（不应再出现，compute_status 必传）。
    """
    if not refs or not measurement:
        return False
    rec = (measurement.get("features") or {}).get(rel)
    if not rec or rec.get("result") != "pass":
        return False
    if fingerprint is not None:
        return rec.get("fingerprint") == fingerprint
    return True


def has_tests(refs: list[str]) -> bool:
    return any(r.endswith((".py", ".spec.ts")) for r in refs)


def compute_status(
    path: Path,
    *,
    measurement: dict | None = None,
    signed_features: set[str] | None = None,
) -> dict:
    """返回 {rel, wave, status, signed, green, refs, deferred}。status 现算，不存。"""
    rel = feature_rel(path)
    wave = feature_wave(path)
    deferred = _deferred_reason(path)
    if deferred is not None:
        return {"rel": rel, "wave": wave, "status": "Backlog", "signed": False,
                "green": False, "refs": [], "deferred": deferred}

    _, pytest_val, _twin_f = _parse_feature_header(path)
    refs = test_refs(pytest_val)
    if measurement is None:
        measurement = load_measurement()
    if signed_features is None:
        signed_features = load_signoff_features()

    g = green(rel, refs, measurement, feature_fingerprint(path))
    s = rel in signed_features

    if s and g:
        status = "Done"
    elif s and not g:
        status = "Ready"
    elif (not s) and (g or has_tests(refs)):
        status = "InTest"
    else:
        status = "Draft"

    return {"rel": rel, "wave": wave, "status": status, "signed": s,
            "green": g, "refs": refs, "deferred": None}


def compute_all() -> list[dict]:
    measurement = load_measurement()
    signed = load_signoff_features()
    return [compute_status(p, measurement=measurement, signed_features=signed)
            for p in all_features()]
