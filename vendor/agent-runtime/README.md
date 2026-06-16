# AgentRuntime 离线安装包（vendor）

zw-brain Docker 镜像与本地 Embedded 开发均使用此目录下的 **pyc-only 离线包**，不再依赖仓库外的 `../agent-runtime` 源码。

## 包位置

```text
release/v1.1.2.2/agent-runtime-1.1.2.2-py312-pyc-only.tar.gz
```

- Python：**3.12**（minor 须与构建机一致）
- 版本：**1.1.2.2**

## 本地安装（当前 Python 环境）

```bash
cd /path/to/zw-brain/vendor/agent-runtime/release/v1.1.2.2
sha256sum -c agent-runtime-1.1.2.2-py312-pyc-only.tar.gz.sha256  # 校验失败必须停止安装
tar -xzf agent-runtime-1.1.2.2-py312-pyc-only.tar.gz
cd agent-runtime-1.1.2.2-py312-pyc-only
uv pip install -r requirements.txt -r ../../../requirements-deepagents.txt
./install.sh
python -c "from agent_runtime import RuntimeService; print('ok')"
```

`AGENT.yaml` 校验 schema 见仓库根目录 `schemas/agent.schema.json`（与离线包版本对齐）。
API 与接入指南见 [`docs/agent-runtime/`](../../docs/agent-runtime/)（单一源，离线包不重复维护文档副本）。

## 升级

替换 `release/v1.1.2.2/` 下 tar.gz 后必须同步更新 `*.tar.gz.sha256`：

```bash
cd vendor/agent-runtime/release/v1.1.2.2
shasum -a 256 agent-runtime-1.1.2.2-py312-pyc-only.tar.gz \
  | awk '{print $1"  agent-runtime-1.1.2.2-py312-pyc-only.tar.gz"}' \
  > agent-runtime-1.1.2.2-py312-pyc-only.tar.gz.sha256
```

同步更新 `schemas/agent.schema.json`，并调整 `Dockerfile` 中的 `AGENT_RUNTIME_EXTRACT_DIR`（若目录名变更）。
