#!/usr/bin/env python3
"""Regenerate the WebUI demo seed (zw_brain/domain/seed_snapshot.json) from
real legacy data already imported into .data/zw_brain.db.

Covers four surfaces (A1-A4 of docs/reconstructs/legacy-import-mapping-v1.md §五):

- A1 真政务案例 → discovery.resources (10 cards from dsp_example.data_example)
- A2 真目录召回字典 → discovery.catalogTree + discovery.recallDictionary
- A3 真组织/区划 projection → audit_events + workbench role greetings
- A4 完整业务旅程端到端 demo → requests + approvals + delivery_tasks + disputes

Idempotent: rerunning produces the same output regardless of prior state.
Touches ONLY the keys listed above; all other hand-authored UI affordances
(provider/dashboard/alerts/tickets/knowledge_articles/...) are preserved.

Usage:
    .venv/bin/python scripts/import_legacy_dumps.py import <schema>  # populate DB
    .venv/bin/python scripts/build_true_data_seed.py                  # regen seed
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = REPO_ROOT / ".data" / "zw_brain.db"
SEED_PATH = REPO_ROOT / "zw_brain" / "domain" / "seed_snapshot.json"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise SystemExit(
            f"DB not found at {DB_PATH}; run scripts/import_legacy_dumps.py import <schema> first"
        )
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _load_topic_packages(con: sqlite3.Connection) -> list[dict]:
    """Return the 10 real topic packages with parsed JSON snapshots."""
    rows = con.execute(
        "SELECT package_code, title, status, scenario, owner_org_snapshot_json, "
        "display_snapshot_json, source_ref FROM topic_package ORDER BY title"
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["owner"] = json.loads(d.pop("owner_org_snapshot_json"))
        d["display"] = json.loads(d.pop("display_snapshot_json"))
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# A1 — discovery.resources (10 cards)
# ---------------------------------------------------------------------------

# Curated case-specific copy keyed by topic-package title. Title is the most
# stable key across re-imports of the legacy dump (32-char hex package_codes
# are theoretically stable but harder to audit at a glance, and degrade
# silently to the generic template when they drift). Titles are copied
# verbatim from dsp_example.data_example.
CASE_OVERRIDES: dict[str, dict] = {
    "公司变更登记": {
        "zone": "营商环境专区",
        "fields": ["统一社会信用代码", "企业名称", "变更类型", "登记时间", "登记机关"],
        "explain": [
            "命中 dsp_example.data_example 真政务案例：公司变更登记",
            "field_type=01（涉企登记），适合做企业开办/变更链路演示",
            "已通过 verify --strict（resolved）",
        ],
        "next": ["发起涉企登记复用申请", "查看营商环境专区", "对齐上级一表通口径"],
    },
    "不动产交易登记一体化平台": {
        "zone": "民生保障专区",
        "fields": ["不动产单元编号", "交易当事人", "登记类型", "办理结果", "回流时间"],
        "explain": [
            "真政务案例：不动产交易登记一体化平台（status=rejected）",
            "field_type=04（不动产/房屋），适合做拒批回流路径演示",
            "已被旧平台明确拒绝，可作为反面教材展示制度执行边界",
        ],
        "next": ["查看驳回原因与改进路径", "进入民生保障专区", "查看不动产相关目录"],
    },
    "出生一件事": {
        "zone": "民生保障专区",
        "fields": ["新生儿编号", "出生时间", "出生医学证明", "户籍登记", "母婴档案"],
        "explain": [
            "真政务案例：出生一件事（status=published, opinion=通过）",
            "field_type=11,16（人口与教育跨域），跨部门一表通典型",
            "可作为 申请人 个人专题“一件事”链路标杆",
        ],
        "next": ["进入“一件事”专题包", "查看跨部门字段对齐", "申请人口基础信息复用"],
    },
    "小微企业一次性创业岗位开发补贴申领": {
        "zone": "营商环境专区",
        "fields": ["企业名称", "统一社会信用代码", "新增岗位数", "补贴金额", "申领时间"],
        "explain": [
            "真政务案例：小微企业一次性创业岗位开发补贴申领（submitted）",
            "field_type=05（创业就业），适合做小微企业惠企政策链演示",
            "已沉淀进真共享专区，可做 申请人→镇街填报人 联审标杆",
        ],
        "next": ["发起补贴复用申请", "查看小微企业惠企专题", "对齐人社部门数据口径"],
    },
    "数据查询创新应用": {
        "zone": "治理减负专区",
        "fields": ["业务系统名称", "目录覆盖范围", "查询频次", "命中率", "字段缺口"],
        "explain": [
            "真政务案例：数据查询创新应用（published, opinion=通过）",
            "field_type=03,11,15,16（民政/人口/民生/教育跨域），跨域共享治理示范",
            "适合作为“先复用后补差异”治理减负主线演示",
        ],
        "next": ["查看跨域字段缺口报告", "进入治理减负专区", "对齐民政/人社查询口径"],
    },
    "中小学新生入学“一件事一次办”": {
        "zone": "民生保障专区",
        "fields": ["学籍编号", "入学年份", "户籍信息", "学区编码", "家长联系方式"],
        "explain": [
            "真政务案例：中小学新生入学“一件事一次办”（published, opinion=通过）",
            "field_type=05（教育），落地教育条线减负典型",
            "可作为基层报表减负示范专题包",
        ],
        "next": ["进入教育条线专题包", "对齐学籍/户籍口径", "查看减负看板"],
    },
    "婚姻登记“全省通办”": {
        "zone": "民生保障专区",
        "fields": ["婚姻状态", "登记机关", "登记时间", "户籍同步状态", "异地办理标识"],
        "explain": [
            "真政务案例：婚姻登记“全省通办”（published）",
            "field_type=11（婚育），强同步、跨地区协同典型",
            "适合做“数据替群众跑”的演示主线",
        ],
        "next": ["查看跨地区同步链路", "进入民生保障专区", "对齐民政/公安数据口径"],
    },
    "行政审批服务帮办代办": {
        "zone": "营商环境专区",
        "fields": ["事项名称", "代办人员", "受理状态", "办结时限", "群众反馈"],
        "explain": [
            "真政务案例：行政审批服务帮办代办（published, opinion=同意）",
            "field_type=01（涉企/审批），适合做帮办代办链路演示",
            "可作为基层帮办代办看板素材",
        ],
        "next": ["进入营商环境专区", "查看帮办代办专题包", "对齐审批口径"],
    },
    "测试案例": {"skip": True},
}


# Hand-curated narrative for the parking topic package. Preserves the rich
# storyline (now in seed_snapshot.json) under a real legacyId key.
PARKING_STORYLINE_PROVINCE = {
    # NOTE: id deliberately kept as `res-jbxx-ledger` (legacy slot)
    # because BrainService._sync_state_views and test fixtures look it up by
    # this exact id. Renaming would force a cross-cutting test+code change.
    "id": "res-jbxx-ledger",
    "legacyId": "370000308004000000/000001",
    "name": "停车场信息共享目录",
    "provider": "省大数据局",
    "providerOrgCode": "11370000MB284651XL",
    "zone": "营商环境专区",
    "status": "可复用",
    "score": 99,
    "updatedAt": "2026-04-27",
    "subscribers": 31,
    "approvalRate": "97%",
    "coverage": "真目录：2 个资源",
    "desc": "来自旧平台 dsp_catalog 的真实目录“停车场信息”（370000308004000000/000001），已关联库表资源与文件资源，可作为城市治理、交通运行和一网通办场景的默认复用入口。",
    "fields": [
        "停车场编号", "停车场名称", "所属区域", "泊位总数",
        "开放状态", "更新时间", "资源类型", "责任单位",
    ],
    "explain": [
        "命中真目录：停车场信息",
        "已从 dump 验证库表/文件两类资源存在",
        "适合作为“先复用目录资源，再补本地差异”的客户级演示主线",
    ],
    "nextHints": [
        "发起停车场信息复用申请",
        "查看目录与资源来源",
        "进入营商环境专区",
    ],
    "trueData": {
        "source_schema": "dsp_catalog",
        "catalog_code": "370000308004000000/000001",
        "catalog_title": "停车场信息",
        "owner_org_id": "11370000MB284651XL",
        "owner_org_name": "省大数据局",
        "region_code": "370000000000",
        "region_name": "山东省",
        "resource_codes": [
            "39a41e4b4e80439187e0f86218bae5d9",
            "486fad4640fb44589c05f72df23650d7",
        ],
        "legacy_mapping_status": "resolved",
    },
}

LEGACY_PLACEHOLDER_CARDS = [
    {
        # Kept for test fixtures (tests/test_brain_service.py, test_rest_runtime.py
        # etc.) — these reference `res-market-activity` as a stable id for
        # `application.resource.submit` flows. Migrating tests to real-data ids
        # is a separate task.
        "id": "res-market-activity",
        "name": "市场主体活跃度月度汇总",
        "provider": "市市场监管局",
        "zone": "营商环境专区",
        "status": "可申请",
        "score": 88,
        "updatedAt": "2026-04-23",
        "subscribers": 19,
        "approvalRate": "93%",
        "desc": "适合营商环境趋势分析，但不替代法人主体基础信息模板本身。",
        "fields": ["统计月", "区县", "新增主体数", "注销主体数", "净增长"],
        "explain": [
            "适合做趋势结果，但不是当前复用起点",
            "更适合作为模板复用后的专题补充",
        ],
        "nextHints": ["作为专题补充资源查看"],
        "coverage": "趋势汇总",
    },
    {
        "id": "res-company-visit",
        "name": "企业走访差异补录视图",
        "provider": "镇街协同填报链路",
        "zone": "治理减负专区",
        "status": "可查看",
        "score": 81,
        "updatedAt": "2026-04-24",
        "subscribers": 11,
        "approvalRate": "—",
        "desc": "聚合基层补录频次最高的现场差异字段，用于反向指导模板升级与减负治理。",
        "fields": ["经营状态", "最近走访时间", "现场备注"],
        "explain": [
            "用于观察哪些字段仍需基层反复补录",
            "适合进入治理视角，不是普通需求的起点",
        ],
        "nextHints": ["查看减负热区"],
        "coverage": "治理视图",
    },
]


PARKING_STORYLINE_CITY = {
    "id": "res-parking-chengdu",
    "legacyId": "370000307001040000/000003",
    "name": "停车场信息表（市级目录样本）",
    "provider": "市交通运输局",
    "providerOrgCode": "00510103",
    "zone": "营商环境专区",
    "status": "可申请",
    "score": 92,
    "updatedAt": "2026-04-27",
    "subscribers": 7,
    "approvalRate": "—",
    "coverage": "真目录：市级表",
    "desc": "来自真 dump 的“停车场信息表”（370000307001040000/000003），可作为跨地区目录对齐和上级汇聚演示的候选资源。",
    "fields": ["停车场名称", "区县", "泊位数", "运营状态", "更新时间"],
    "explain": [
        "与省级停车场信息目录同名同域",
        "适合演示跨层级目录汇聚",
        "需在申请前确认责任部门与字段口径",
    ],
    "nextHints": ["查看跨地区口径", "作为候选资源匹配"],
    "trueData": {
        "source_schema": "dsp_catalog",
        "catalog_code": "370000307001040000/000003",
        "catalog_title": "停车场信息表",
        "owner_org_id": "00510103",
        "owner_org_name": "市交通运输局",
        "region_code": "005101",
        "region_name": "成都市",
        "legacy_mapping_status": "resolved",
    },
}


def _resource_id_from_title(title: str) -> str:
    """Stable, URL-safe id derived from package title."""
    slug = (
        title.replace("“", "")
        .replace("”", "")
        .replace("（", "-")
        .replace("）", "")
        .replace(" ", "-")
        .replace("/", "-")
        .replace("一件事一次办", "yjs-yco")
        .replace("一件事", "yjs")
        .replace("全省通办", "qstb")
    )
    return f"res-tp-{slug[:24]}"


def _build_a1_resources(packages: list[dict]) -> list[dict]:
    """Build discovery cards: 2 parking storyline + 8 from data_example +
    2 legacy placeholder cards (LEGACY_PLACEHOLDER_CARDS).

    Total = 10 real-data cards + 2 legacy cards = 12. The "A1 真政务案例 ×10"
    deliverable is fulfilled by the 2 parking + 8 dsp_example cases; the legacy
    placeholders remain visible in the WebUI as supporting context until the
    test suite (which references their ids) migrates to real-data ids.
    """
    cards: list[dict] = [PARKING_STORYLINE_PROVINCE, PARKING_STORYLINE_CITY]

    for pkg in packages:
        ov = CASE_OVERRIDES.get(pkg["title"], {})
        if ov.get("skip"):
            continue
        # Skip the parking topic package — it's already covered by the rich
        # storyline cards above (we don't want to dilute the parking narrative).
        if "停车场" in pkg["title"]:
            continue
        own = pkg["owner"]
        disp = pkg["display"]
        summary = (disp.get("summary") or "").strip()
        # Trim HTML wrappers from raw rich-text dump fields
        if summary.startswith("<p>") and summary.endswith("</p>"):
            summary = summary[3:-4]
        # Truncate overlong descriptions for card display
        if len(summary) > 120:
            summary = summary[:117] + "…"
        status_zh = {
            "published": "可复用",
            "submitted": "已提交",
            "rejected": "已驳回",
        }.get(pkg["status"], pkg["status"])

        card = {
            "id": _resource_id_from_title(pkg["title"]),
            "legacyId": pkg["package_code"],
            "name": pkg["title"],
            "provider": own.get("org_name") or "省大数据局",
            "providerOrgCode": own.get("org_code"),
            "zone": ov.get("zone", "营商环境专区"),
            "status": status_zh,
            "score": 95 if pkg["status"] == "published" else 85,
            "updatedAt": "2026-04-27",
            "subscribers": 0,
            "approvalRate": "—",
            "coverage": f"真案例：dsp_example/{pkg['package_code'][:8]}",
            "desc": summary or pkg["title"],
            "fields": ov.get("fields", []),
            "explain": ov.get("explain", [
                f"真政务案例：{pkg['title']}",
                f"field_type={disp.get('field_type','')}",
                f"导入状态：{pkg['status']}",
            ]),
            "nextHints": ov.get("next", ["发起复用申请", "查看真案例来源"]),
            "trueData": {
                "source_schema": "dsp_example",
                "package_code": pkg["package_code"],
                "owner_org_id": own.get("org_code"),
                "owner_org_name": own.get("org_name"),
                "region_code": own.get("region_code"),
                "region_name": own.get("region_name"),
                "topic_status": pkg["status"],
                "field_type": disp.get("field_type"),
                "legacy_mapping_status": "resolved",
            },
        }
        cards.append(card)

    cards.extend(LEGACY_PLACEHOLDER_CARDS)
    return cards


# ---------------------------------------------------------------------------
# A2 — discovery.catalogTree + discovery.recallDictionary
# ---------------------------------------------------------------------------

# Top categories in dsp_basesubject.basesubject_info — these are the real
# subject classifications the legacy platform organises catalogs by. Codes are
# stable across dumps; labels copied verbatim from the dump.
BASESUBJECT_CATEGORIES = [
    {"code": "01", "name": "涉企登记许可"},
    {"code": "03", "name": "民政民生"},
    {"code": "04", "name": "不动产/房屋"},
    {"code": "05", "name": "教育就业创业"},
    {"code": "11", "name": "婚育人口"},
    {"code": "15", "name": "民生保障"},
    {"code": "16", "name": "教育条线"},
    {"code": "17", "name": "其他"},
]


def _build_a2_catalog_tree(con: sqlite3.Connection, total_topic_packages: int) -> list[dict]:
    """Real-distribution catalogTree: counts come from the imported DB."""
    catalog_total = con.execute(
        "SELECT COUNT(*) FROM catalog_entry"
    ).fetchone()[0]
    org_total = con.execute("SELECT COUNT(*) FROM org_projection").fetchone()[0]
    region_total = con.execute(
        "SELECT COUNT(*) FROM region_projection"
    ).fetchone()[0]
    return [
        {"name": "真政务案例（dsp_example）", "count": total_topic_packages},
        {"name": "共享目录条目（dsp_catalog）", "count": catalog_total},
        {"name": "组织 projection（dsp_bsp.pub_organ）", "count": org_total},
        {"name": "区划 projection（dsp_bsp.pub_region）", "count": region_total},
    ]


# F9 Z2/Z3 catalog-line seeding (D34.c): deterministically surface these real
# sd-default medical-insurance catalogs in the recall dictionary so J1 找数
# search recalls them. They are real `catalog_entry` rows (basic_element class);
# without an explicit include the 5-char "医保码信息" falls below the length>=6
# sampler floor and the 异地就医* titles may miss the top-25 length-ordered cut.
# Fields are read from the DB (real owner_org_id / lifecycle_status) — no invention.
PRIORITY_RECALL_TITLES = [
    "医保码信息",
    "异地就医统筹区开通信息",
    "异地就医定点医疗机构信息",
    "异地就医经办机构信息",
]


def _build_a2_recall_dictionary(con: sqlite3.Connection) -> dict:
    """NL-skill recall dictionary: top categories + sample titles.

    Only `active` and `approved_pending_publish` catalogs feed the dictionary —
    retired/draft entries would point users at obsolete or unstable resources.
    """
    import re

    sample_titles: list[dict] = []
    seen: set[str] = set()

    # Priority include (deterministic): real medical-insurance catalogs from DB.
    for title in PRIORITY_RECALL_TITLES:
        row = con.execute(
            "SELECT title, owner_org_id, lifecycle_status FROM catalog_entry "
            "WHERE title = ? AND lifecycle_status IN ('active', 'approved_pending_publish') "
            "LIMIT 1",
            (title,),
        ).fetchone()
        if row is None or row["title"] in seen:
            continue
        seen.add(row["title"])
        sample_titles.append(
            {
                "title": row["title"],
                "owner_org_id": row["owner_org_id"],
                "lifecycle_status": row["lifecycle_status"],
            }
        )

    for r in con.execute(
        "SELECT title, owner_org_id, lifecycle_status FROM catalog_entry "
        "WHERE title IS NOT NULL AND length(title) BETWEEN 6 AND 30 "
        "  AND lifecycle_status IN ('active', 'approved_pending_publish') "
        "ORDER BY length(title) DESC, title"
    ):
        t = r["title"]
        if not t or t in seen:
            continue
        if re.fullmatch(r"[A-Za-z0-9_/-]+", t):
            continue
        seen.add(t)
        sample_titles.append(
            {
                "title": t,
                "owner_org_id": r["owner_org_id"],
                "lifecycle_status": r["lifecycle_status"],
            }
        )
        if len(sample_titles) >= 25:
            break

    return {
        "categories": BASESUBJECT_CATEGORIES,
        "sample_titles": sample_titles,
        "source": "dsp_catalog.data_catalog (via importer.catalog_entry)",
        "purpose": "NL skill 召回字典：用户搜“人口/不动产/停车场/婚姻/小微企业”等关键词时，召回真目录候选",
    }


# ---------------------------------------------------------------------------
# A3 — audit_events + workbench role greetings
# ---------------------------------------------------------------------------

def _build_a3_audit_events() -> list[dict]:
    """Audit events with real org actors and real catalog refs.

    Preserves the existing chronology shape; replaces synthetic actor strings.
    """
    return [
        {
            "id": "AE-2026-04-25-0902",
            "time": "04-25 09:02",
            "actor": "system",
            "type": "discovery.template-match",
            "target": "停车场信息共享目录 / 370000308004000000/000001",
            "result": "ok",
            "chain": "pending",
        },
        {
            "id": "AE-2026-04-25-0914",
            "time": "04-25 09:14",
            "actor": "省大数据局 / 平台管理员",
            "type": "application.submit",
            "target": "REQ-2026-04-25-0011（停车场信息复用）",
            "result": "ok",
            "chain": "pending",
        },
        {
            "id": "AE-2026-04-26-1015",
            "time": "04-26 10:15",
            "actor": "省大数据局 / 资源审核员",
            "type": "application.review.start",
            "target": "REQ-2026-04-26-0006（婚姻登记“全省通办”）",
            "result": "in_progress",
            "chain": "pending",
        },
        {
            "id": "AE-2026-04-26-1402",
            "time": "04-26 14:02",
            "actor": "省公安厅 / 信息员",
            "type": "objection.raised",
            "target": "OBJ-数据目录纠错_信息项中缺少抽检时间字段",
            "result": "provider_investigating",
            "chain": "pending",
        },
        {
            "id": "AE-2026-04-27-0903",
            "time": "04-27 09:03",
            "actor": "省大数据局 / 数据治理岗",
            "type": "delivery.task.granted",
            "target": "DLV-2026-04-27-0003（出生一件事推送链路）",
            "result": "ok",
            "chain": "anchored",
        },
        {
            "id": "AE-2026-04-27-1148",
            "time": "04-27 11:48",
            "actor": "济南市大数据局 / 区县协同员",
            "type": "delivery.attempt.completed",
            "target": "EXEC-START_EXCHANGE_TABLE_JOB-通道1（NIFI）",
            "result": "ok",
            "chain": "pending",
        },
        {
            "id": "AE-2026-04-27-1530",
            "time": "04-27 15:30",
            "actor": "省人力资源社会保障厅 / 业务对接人",
            "type": "subscription.confirm",
            "target": "REQ-2026-04-27-0021（小微企业岗位补贴）",
            "result": "ok",
            "chain": "pending",
        },
        {
            "id": "AE-2026-04-28-0830",
            "time": "04-28 08:30",
            "actor": "platform / 异议复核",
            "type": "objection.resolved",
            "target": "OBJ-停车场信息文件资源显示不全",
            "result": "resolved",
            "chain": "anchored",
        },
    ]


def _augment_workbench(workbench: dict) -> dict:
    """Strip fabricated greetings (idempotent rewrite); keep subtitle real-org context.

    #258 复审 R-004：问候语里的 seed 虚构人物名（周处长/区县协同员/审计员…）违 D11
    真实库精神，已整体退役——greeting 不再入 seed，由 workbench.view handler 按当前
    会话身份现算（actor_snapshot.display_name + 时段问候，取不到诚实回落纯时段问候）。
    todos/highlights 结构保持不动。
    """
    new_wb = json.loads(json.dumps(workbench))  # deep copy
    # 2026-05-19 retrofit (D23): workbench bucket keys 对齐新 ROLE_* 6 角色
    for bucket in new_wb.values():
        if isinstance(bucket, dict):
            bucket.pop("greeting", None)
    if "ROLE_ORGAN_OPERATER" in new_wb:
        new_wb["ROLE_ORGAN_OPERATER"]["subtitle"] = (
            "你有 1 条停车场信息复用申请待看进度；本周共有 10 条来自 dsp_example 的真政务案例可被订阅；"
            "1 条减负提示来自约 1.8 万条 pub_organ projection。"
        )
    if "ROLE_ORGAN_MANAGER" in new_wb:  # 旧 r3 镇街/区县协同员 → ORGAN_MANAGER 部门管理员
        new_wb["ROLE_ORGAN_MANAGER"]["subtitle"] = (
            "本周 2 条由省大数据局发起的婚姻登记/出生一件事流转任务等你确认；停车场信息已通过基础目录审核。"
        )
    if "ROLE_SECURITY_AUDIT" in new_wb:  # 旧 r5 审计员 → SECURITY_AUDIT
        new_wb["ROLE_SECURITY_AUDIT"]["subtitle"] = (
            "本周 8 条审计事件已锚定（2 条 anchored / 6 pending）；其中 1 条与省公安厅发起的目录异议相关。"
        )
    return new_wb


# ---------------------------------------------------------------------------
# A4 — disputes（1 objection；申请三键拼接已随 Action D 退役）
# ---------------------------------------------------------------------------

# Action D + C-1：演示单拼接退役——requests / approvals / delivery_tasks 快照键已随
# 写路径单源化整体退役（运行时单一律真实创建、经 CardSession 直落 DB），seed 不再
# 携带、本生成器不再拼接捏造演示链（D47 删演示单口径）。disputes 快照键仍 live。

NEW_DISPUTES: list[dict] = [
    {
        "id": "DSP-2026-04-26-OBJ-PUBSEC",
        "title": "数据目录纠错_信息项中缺少抽检时间字段",
        "severity": "mid",
        "status": "provider_investigating",
        "owner": "省公安厅 / 信息员（投诉方）→ 省大数据局（提供方）",
        "timeline": [
            {"time": "04-26 14:02", "label": "省公安厅信息员提出异议"},
            {"time": "04-26 17:18", "label": "省大数据局接单 → provider_investigating"},
        ],
        "aiSummary": "建议在不动产/抽检类目录上统一补“抽检时间”字段口径；可作为 dsp_catalog 字段治理候选。",
    },
]


# Legacy provider-side placeholder entries kept for test fixtures.
# Tests in test_brain_service.py and test_read_models.py call
# `resource.manage_asset` against `res-company-visit` and assume that id
# exists in `provider.resources`.
LEGACY_PROVIDER_RESOURCES = [
    {
        "id": "res-company-visit",
        "name": "企业走访差异补录视图",
        "status": "待审核",
        "type": "治理视图",
        "updatedAt": "2026-04-24",
    },
    {
        "id": "res-market-activity",
        "name": "市场主体活跃度月度汇总",
        "status": "可共享",
        "type": "专题资源",
        "updatedAt": "2026-04-23",
    },
]


def _wire_provider_legacy_resources(snapshot: dict) -> None:
    """Ensure provider.resources contains the legacy placeholder ids that
    tests still depend on. Idempotent — won't add duplicates."""
    provider = snapshot.setdefault("provider", {})
    resources = provider.setdefault("resources", [])
    existing_ids = {r["id"] for r in resources}
    for legacy in LEGACY_PROVIDER_RESOURCES:
        if legacy["id"] not in existing_ids:
            resources.append(legacy)


def _wire_new_chains(snapshot: dict) -> None:
    """Splice the objection dispute chain into the disputes array.

    Idempotent: if entries with the same id already exist, replace them.
    """

    def _upsert_by_id(arr: list[dict], items: list[dict]) -> list[dict]:
        existing_by_id = {x["id"]: i for i, x in enumerate(arr)}
        out = list(arr)
        for it in items:
            if it["id"] in existing_by_id:
                out[existing_by_id[it["id"]]] = it
            else:
                out.append(it)
        return out

    # Action D：requests / approvals / delivery_tasks 快照键退役，不再拼接；
    # 申请链路一律运行时真实创建（CardSession 直落 DB）。
    snapshot["disputes"] = _upsert_by_id(snapshot.get("disputes", []), NEW_DISPUTES)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    snapshot = json.loads(SEED_PATH.read_text(encoding="utf-8"))

    with _connect() as con:
        packages = _load_topic_packages(con)
        # A1
        snapshot["discovery"]["resources"] = _build_a1_resources(packages)
        # A2
        snapshot["discovery"]["catalogTree"] = _build_a2_catalog_tree(con, len(packages))
        snapshot["discovery"]["recallDictionary"] = _build_a2_recall_dictionary(con)
        # A3
        snapshot["audit_events"] = _build_a3_audit_events()
        snapshot["workbench"] = _augment_workbench(snapshot.get("workbench", {}))
        # A4
        _wire_new_chains(snapshot)
        # Test-fixture compat: ensure legacy provider ids remain reachable.
        _wire_provider_legacy_resources(snapshot)

    SEED_PATH.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {SEED_PATH.relative_to(REPO_ROOT)}: "
        f"discovery.resources={len(snapshot['discovery']['resources'])} "
        f"catalogTree={len(snapshot['discovery']['catalogTree'])} "
        f"recallDictionary.sample_titles={len(snapshot['discovery']['recallDictionary']['sample_titles'])} "
        f"audit_events={len(snapshot['audit_events'])} "
        f"disputes={len(snapshot['disputes'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
