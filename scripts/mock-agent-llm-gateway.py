#!/usr/bin/env python3
"""Local OpenAI-compatible gateway for AgentRuntime UI acceptance.

This is a deterministic development gateway, not a production model provider.
It returns short business-shaped answers based on the AgentRuntime system prompt
so local UI audits can verify wording, routing and assistant surfaces without
showing generic debug text.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

AGENT_HINTS: dict[str, tuple[str, str]] = {
    "审核研判副驾": ("申请受理和审核人员", "申请详情、审批详情与依据摘要"),
    "审计调查副驾": ("安全审计人员", "审计事件、异常扫描和追责反查"),
    "目录编制向导": ("供数方目录编制人员", "目录模型、字段口径和重复风险"),
    "资源挂接发布体检": ("供数方发布前检查人员", "目录状态、资源详情和字段映射"),
    "权限合规自查副驾": ("平台运维与安全审计人员", "角色、用户、能力矩阵和审计事件"),
    "用数全程副驾": ("用数方申请与交付跟踪人员", "申请草拟、状态跟踪和交付对账"),
    "元数据补齐副驾": ("供数方元数据维护人员", "资源 schema、目录项映射和目录条目"),
    "异议分诊副驾": ("异议受理与核查人员", "异议案件、过程、指标和证据链"),
    "运营报表副驾": ("业务运营与平台运维人员", "目录、交换、服务调用和投影状态"),
    "供需匹配副驾": ("供需对接人员", "需求列表、意图解析和相似目录推荐"),
    "平台使用指南": ("平台各岗位用户", "平台使用、部署、权限和数据共享流程"),
    "数据发现副驾": ("用数方找数人员", "一句话诉求、资源检索和 TOP-N 推荐"),
    "法人信用画像核验": ("授权用数方信用尽调人员", "法人登记、经营、纳税、参保等共享数据"),
    "材料免提交核验编排": ("政务服务材料核验人员", "事项、材料和共享资源目录"),
    "一件事一次办导办": ("政务服务导办人员", "事项、材料和数据复用说明"),
    "双随机靶向抽查名单研判": ("监管抽查研判人员", "法人画像、处罚、信用标签和行业基准"),
    "社会组织监管异常预警": ("社会组织监管研判人员", "登记信息、法人异常和信用标签目录"),
    "重大危险源融合研判": ("公共安全研判人员", "重大危险源、企业画像和隐患目录"),
    "安全生产许可证体检": ("安全生产合规核验人员", "安全生产许可、环境隐患和企业画像"),
    "区域经济运行月度研判": ("经济运行分析人员", "GDP、纳税、法人统计和行业基准"),
    "产业链与规上企业洞察": ("产业分析人员", "法人统计画像、行业分布和企业登记目录"),
    "区域 GDP 税收联动洞察": ("经济税收分析人员", "区域 GDP、税收、企业规模和纳税信用"),
    "停车一张图服务研判": ("城市治理停车服务人员", "停车场信息、车辆状态和服务调用目录"),
    "停车文件完整性核验": ("城市治理数据核验人员", "停车文件资源、schema 和字段映射"),
    "交通工程竣工交换对账": ("交通工程数据对账人员", "竣工验收资源、交付任务和交换统计"),
}


def _content_from_messages(messages: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
    return "\n".join(parts)


def _detect_agent(text: str) -> tuple[str, str, str]:
    for name, (role, evidence) in AGENT_HINTS.items():
        if name in text:
            return name, role, evidence
    return "智能体", "当前岗位人员", "当前岗位可见的数据和只读能力"


def _answer(messages: list[dict[str, Any]]) -> str:
    text = _content_from_messages(messages)
    name, role, evidence = _detect_agent(text)
    return (
        f"## 结论摘要\n"
        f"{name}适合辅助{role}处理需要“先查清依据、再给人工建议”的问题。"
        f"它会围绕{evidence}做只读梳理，不替用户提交、审批、发布或处置。\n\n"
        f"## 适合提问\n"
        f"- 我应该提供哪些编号、时间范围或判断条件？\n"
        f"- 请根据当前可见数据给出研判摘要。\n"
        f"- 还有哪些风险、缺口或下一步人工确认事项？\n\n"
        f"## 边界\n"
        f"以上内容只作为岗位辅助研判，不替代提交、审批、发布或处置。"
        f"需要办结时，请回到对应业务流程由有权限岗位确认。"
    )


class Handler(BaseHTTPRequestHandler):
    def _json(self, status: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _stream_chat_completion(self, *, model: str, content: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        chunks = [content[i : i + 120] for i in range(0, len(content), 120)] or [""]
        for chunk in chunks:
            payload = {
                "id": "zw-brain-local-business-mock",
                "object": "chat.completion.chunk",
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": chunk},
                        "finish_reason": None,
                    }
                ],
            }
            self.wfile.write(f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode())
        final = {
            "id": "zw-brain-local-business-mock",
            "object": "chat.completion.chunk",
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        self.wfile.write(f"data: {json.dumps(final, ensure_ascii=False)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/health", "/v1/health"}:
            self._json(200, {"status": "ok"})
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or "0")
        body = json.loads(self.rfile.read(length) or b"{}")
        messages = body.get("messages") if isinstance(body.get("messages"), list) else []
        content = _answer(messages)
        model = body.get("model") or "mock-chat"
        if body.get("stream") is True:
            self._stream_chat_completion(model=model, content=content)
            return
        self._json(
            200,
            {
                "id": "zw-brain-local-business-mock",
                "object": "chat.completion",
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            },
        )

    def log_message(self, fmt: str, *args: Any) -> None:
        return


def main() -> None:
    host = os.environ.get("ZW_BRAIN_MOCK_AGENT_LLM_HOST", "127.0.0.1")
    port = int(os.environ.get("ZW_BRAIN_MOCK_AGENT_LLM_PORT", "8999"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"mock Agent LLM gateway listening on http://{host}:{port}/v1", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
