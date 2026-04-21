#!/usr/bin/env python3
"""
check_fixture_pii.py — preflight 段 9

强约束（设计基线 §十四 D11）：
    所有 Skill 必须以**旧平台真实业务数据（脱敏）回归验证**——fixture 中
    禁止出现未脱敏的真实 PII（身份证 / 手机 / 邮箱 / 银行卡 / IP），
    禁止出现疑似真实人名 / 单位名作为非脱敏字段。

扫描范围：
    .testing/fixtures/**  下所有 .json / .csv / .yaml / .yml / .txt 文件
    （不存在时 skip）

检测规则：
    1. 18 位身份证（GB 11643-1999 校验位规则不强校验，先按 17 数字 + 1 数字/X
       格式匹配，命中就 fail——脱敏数据应当是 `*` `0` 占位）
    2. 11 位手机号（中国大陆 1[3-9]开头）
    3. 邮箱（不以 @example.* / @test.* / @mock.* 结尾的真实邮箱）
    4. 中国大陆银行卡（13-19 位连续数字，且 Luhn 校验通过）
    5. 真实 IPv4（不在私有段：10/8、172.16/12、192.168/16、127/8）

豁免标记：
    fixture 文件第一行包含 `# pii-check: ignore` → 跳过该文件
    （仅用于显式 mock / 测试人造样本目录）

接入：scripts/preflight.sh 段 9
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

FIXTURE_ROOT = ".testing/fixtures"
TARGET_EXTS = {".json", ".csv", ".yaml", ".yml", ".txt", ".jsonl"}
EXEMPT_MARKER = "pii-check: ignore"

ID_CARD = re.compile(r"\b[1-9]\d{16}[\dXx]\b")
PHONE_CN = re.compile(r"\b1[3-9]\d{9}\b")
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
EMAIL_TEST_DOMAINS = ("example.com", "example.org", "example.net", "test.com", "mock.com", "localhost", "fixture.local")
IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
BANK_CANDIDATE = re.compile(r"\b\d{13,19}\b")


def is_private_ip(ip: str) -> bool:
    parts = ip.split(".")
    if len(parts) != 4:
        return True
    try:
        a, b, _, _ = (int(p) for p in parts)
    except ValueError:
        return True
    if any(int(p) > 255 for p in parts):
        return True  # 不是合法 IP，不算 PII
    if a == 10:
        return True
    if a == 127:
        return True
    if a == 172 and 16 <= b <= 31:
        return True
    if a == 192 and b == 168:
        return True
    return False


def luhn_ok(number: str) -> bool:
    digits = [int(d) for d in number]
    parity = (len(digits) - 2) % 2
    total = 0
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    violations: list[tuple[int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return violations

    header_lines = text.splitlines()[:3]
    if any(EXEMPT_MARKER in line for line in header_lines):
        return violations

    for lineno, line in enumerate(text.splitlines(), start=1):
        # 1) ID card
        for m in ID_CARD.finditer(line):
            val = m.group(0)
            # 全 0 / 全 * / 11111... 等显式占位放行
            if val.startswith("00000") or val.startswith("11111") or "*" in val:
                continue
            violations.append((lineno, "ID_CARD", _redact(line, val)))

        # 2) Phone
        for m in PHONE_CN.finditer(line):
            val = m.group(0)
            if val.startswith("13800138") or val.startswith("19999999") or val.endswith("0000"):
                continue
            violations.append((lineno, "PHONE_CN", _redact(line, val)))

        # 3) Email
        for m in EMAIL.finditer(line):
            val = m.group(0).lower()
            if any(val.endswith(d) for d in EMAIL_TEST_DOMAINS):
                continue
            violations.append((lineno, "EMAIL", _redact(line, val)))

        # 4) Bank candidate (Luhn)
        for m in BANK_CANDIDATE.finditer(line):
            val = m.group(0)
            if 13 <= len(val) <= 19 and luhn_ok(val):
                # 排除全 0 / 1111... / 已被前面 ID_CARD 命中的 18/19 位
                if not (val.startswith("0000") or val.startswith("1111")):
                    if not ID_CARD.fullmatch(val):
                        violations.append((lineno, "BANK_CARD", _redact(line, val)))

        # 5) Public IPv4
        for m in IPV4.finditer(line):
            val = m.group(0)
            if not is_private_ip(val):
                violations.append((lineno, "PUBLIC_IPV4", _redact(line, val)))

    return violations


def _redact(line: str, secret: str) -> str:
    masked = secret[:2] + "*" * max(0, len(secret) - 4) + secret[-2:] if len(secret) > 4 else "*" * len(secret)
    return line.replace(secret, masked).strip()[:140]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    fixtures = repo_root / FIXTURE_ROOT
    if not fixtures.exists():
        print(f"[fixture-pii] skip: {FIXTURE_ROOT}/ not yet created (Phase 0 / Phase 1 task)")
        return 0

    total_files = 0
    total_violations = 0

    for path in fixtures.rglob("*"):
        if not path.is_file() or path.suffix not in TARGET_EXTS:
            continue
        total_files += 1
        violations = scan_file(path)
        if violations:
            total_violations += len(violations)
            rel = path.relative_to(repo_root)
            print(f"\n  ✗ {rel}")
            for lineno, kind, snippet in violations:
                print(f"      L{lineno} [{kind}] {snippet}")

    print()
    if total_violations == 0:
        print(f"[fixture-pii] OK: scanned {total_files} fixture files, no real PII detected")
        return 0
    print(f"[fixture-pii] FAIL: {total_violations} suspected PII instance(s) in {FIXTURE_ROOT}/")
    print("  policy (D11): fixtures MUST be desensitized; replace real values with mask/placeholder")
    print(f"  exempt marker (top of file, sparingly): # {EXEMPT_MARKER}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
