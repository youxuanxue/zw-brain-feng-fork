# 漏扫整改手册（0609）

> 源报告：`old/问题反馈/安全扫描报告-0609/`（主机 `100.69.5.126` 28 条 / `100.112.2.125` 59 条）。
> 本手册把**每一类发现**映射到 根因 → 精确补救 → 归属层，并诚实标注**接受/残留风险**。
> **0610 第二轮复扫核查结果**（哪些已实证生效 / 哪些没生效 / 残留行动）见
> `docs/deployment/security-hardening-0610-rescan.md`。

## 0. 一页结论（上帝视角）

87 条发现看似海量，实只两个根因：

1. **被扫的是未加固的 VM 宿主**，跑着产品根本不需要的服务（CUPS 打印、rpcbind、2013 默认 sshd）。
   zw-brain 以 `python:3.12-slim` 容器交付，容器内**无** cups/rpcbind/sshd——这些发现属宿主、不属产品。
   补救是**减法**：关停/封禁 + sshd 收紧算法。由 `scripts/security/harden-host.sh` 确定性执行。
2. **产品自己的 HTTP 面（:8800）** 漏了两件事：stdlib `http.server` 泄漏 `Python/x.y.z` 版本 banner、
   无安全响应头。已由应用代码修复（`zw_brain/shared/http_security.py` + REST/A2A handler）。

> **诚实边界**：遮蔽版本 banner 会让扫描器不再匹配出 "Python DoS"，但那不是修复 DoS 本身——
> CPython 真正补丁靠**重建镜像**拉取最新 `3.12-slim`。本手册不把"藏 banner"说成"修了 DoS"。

## 1. 整改清单（按发现归类）

| # | 发现（severity） | 端口 | 根因 | 补救 | 归属层 | 状态 |
|---|---|---|---|---|---|---|
| 1 | Diffie-Hellman Ephemeral KEX DoS — D(HE)ater (7.5 高) | 22/2591 | sshd 启用有限域 DHE KEX，可被 CPU 耗尽 | `harden-host.sh`：KexAlgorithms 只留 curve25519/ECDH(+PQC)，去全部 `diffie-hellman-*` | 宿主 | 脚本 |
| 2 | Weak MAC Algorithm(s) (SSH) (2.6 低) | 22/2591 | 启用 hmac-sha1 / umac-64 / md5 | `harden-host.sh`：MACs 仅 `hmac-sha2-*-etm` + `umac-128-etm` | 宿主 | 脚本 |
| 3 | Terrapin Prefix Truncation (CVE-2023-48795) (5.9 中) | 22/2591 | OpenSSH 8.9p1 无 strict-kex + 启用 chacha20-poly1305 / CBC-EtM | **彻底**：升级 OpenSSH≥9.6（OS 包）。**配置级缓解**：`harden-host.sh` Ciphers 去 chacha20-poly1305、只留 GCM+CTR | 宿主 | 脚本(缓解) + OS 升级(彻底) |
| 4 | OpenBSD OpenSSH 多条版本类 (8.1 高 / 6.8 / 5.x 中…) | 22/2591 | OpenSSH 8.9p1 旧于修复版 9.9p2 | 升级发行版 openssh-server 包到最新；信创发行版跟其安全基线 | 宿主 | OS 升级 |
| 5 | OpenSSH Information Disclosure (CVE-2016-20012) (5.3 中) | 22/2591 | 同上，版本类 | 同 #4（OpenSSH 升级） | 宿主 | OS 升级 |
| 6 | RPC Portmapper Public Accessible (6.4 中) + Detection/list (info) | 111 | rpcbind 对外可达（无 NFS 需求却在跑） | `harden-host.sh`：`disable --now` + `mask` rpcbind(+.socket)；确需 NFS 则 `--keep-rpcbind` + 防火墙限源 | 宿主 | 脚本 |
| 7 | CUPS 检测 + BREACH + 自签证书 + HSTS/HPKP missing + cipher 报告（1×5.9 中 + 多 info） | 631 | 后端服务器跑着 CUPS 打印（含其自带 TLS 面） | `harden-host.sh`：`disable --now` + `mask` cups/cups.socket/cups-browsed；确需打印则 `--keep-cups` + 防火墙限本机。**关停后 631 全部发现一并消失** | 宿主 | 脚本 |
| 8 | Python DoS (Dec/Oct 2025) (7.5 高 / 5.x 中) | 8800 | 扫描器据 `Server: …Python/3.12.13` banner 版本匹配 CPython CVE | **应用层**：去版本化 banner（下方 #11）使其不再被匹配。**彻底**：周期性**重建镜像**拉最新 `3.12-slim` patch | 产品(代码+镜像) | 代码✅ + 镜像重建 |
| 9 | HTTP Server Banner / type and version (info) | 8800 | 同上 banner 泄漏 | 同 #11（banner 去版本化） | 产品(代码) | 代码✅ |
| 10 | HTTP Security Headers Detection（缺 CSP/X-Frame/HSTS…）(info) | 8800 | stdlib handler 不发安全头 | **应用层**：`security_headers()` 注入 CSP/X-Frame-Options/X-Content-Type-Options/Referrer-Policy/Permissions-Policy + HTTPS 下 HSTS | 产品(代码) | 代码✅ |
| 11 | （上面 #8/#9 的代码补救） | 8800 | — | `RestHandler.version_string()` 返回 `zw-brain`（不含版本）；A2A 同 | 产品(代码) | 代码✅ |
| 12 | Allowed HTTP Methods Enumeration (info) | 8800/631 | 探测允许的方法 | stdlib 对未实现方法（TRACE/PUT…）默认回 501，无 XST 暴露；:8800 仅 GET/POST。**无需改动** | 产品 | 接受（已安全） |
| 13 | ICMP Timestamp Reply Disclosure (2.1 低) | icmp | 主机回 ICMP type 14 | `harden-host.sh`：nft/iptables drop ICMP timestamp-request/-reply（best-effort）；或边界防火墙 | 宿主 | 脚本(best-effort) |
| 14 | TCP Timestamps Disclosure (2.6 低) | general | TCP 选项暴露 uptime | **接受风险**：关闭 `net.ipv4.tcp_timestamps` 伤 PAWS/RTT，低危。脚本默认不关，留运维评估 | 宿主 | 接受残留 |
| 15 | CPE Inventory / Hostname / OS Detection / Traceroute / Services / SSH 协议算法报告 等 (0.0 info) | 多 | 纯指纹/资产识别，非漏洞 | 无需整改（信息级）；攻击面随 #1-#7 收敛后自然减少 | — | 接受（info） |

## 2. 执行步骤

### 2.1 产品层（已在本次 PR 落地，随镜像发布生效）
- `zw_brain/shared/http_security.py`：banner 与安全头单一事实源。
- `zw_brain/entry/rest/server.py`、`zw_brain/entry/a2a/server.py`：`version_string()` + `end_headers()` 收口。
- `Dockerfile`：runtime 阶段 OS 包安全升级；CPython 补丁靠周期性重建（注释已写明）。
- **CPython DoS 彻底化**：发布流程定期 `docker build`（基础镜像 tag 不 pin、滚动拉最新 3.12.x），或在出现高危 CPython CVE 时立即重建。

### 2.2 宿主层（部署/运维在被扫主机执行）
```bash
# 1) 先 DRY-RUN，看清将做什么，不改任何东西
sudo bash scripts/security/harden-host.sh

# 2) 审阅无误后执行；从**另一终端**确认 SSH 仍可登录后再断开当前会话
sudo bash scripts/security/harden-host.sh --apply

# 如本机确需打印/NFS，分别用 --keep-cups / --keep-rpcbind 保留并改用防火墙限源
```
脚本特性：默认 dry-run、`--apply` 才动手、每改文件先备份 `*.zw-bak-<ts>`、幂等、`sshd -t` 校验通过才 reload、结尾自检打印最终算法与服务状态。

### 2.3 OpenSSH 次版本升级（#4/#5，脚本不代劳）
属 OS 包管理动作，跟发行版安全基线：
```bash
# Debian/Ubuntu
sudo apt-get update && sudo apt-get install --only-upgrade openssh-server
# RHEL/CentOS/Kylin/UOS 等
sudo yum update openssh-server   # 或 dnf
```

## 3. 接受/残留风险（明确登记，不偷偷略过）
- **TCP timestamps（#14，低危 2.6）**：默认保留，关闭损 PAWS/性能，运维按需 `net.ipv4.tcp_timestamps=0`。
- **Terrapin 配置级缓解 vs 彻底修复（#3）**：脚本收紧算法已消除可利用面；根治需 OpenSSH≥9.6。
- **容器非 root 化**：与 `/data` 卷首启 `drop_all+create_all` 建 schema 的写权限耦合，引入需配套 chown/initContainer，列为后续债（见 `docs/preflight-debt.md`），本期不引入以免破坏首启。
- **信息级指纹（#15）**：保留，攻击面随高/中危收敛后下降，不单独整改。

## 4. 复扫验收口径
- :8800 `curl -sI` → `Server: zw-brain`（无 `Python/`）、含 CSP/X-Frame-Options/X-Content-Type-Options/Referrer-Policy/Permissions-Policy；经 TLS 代理（`X-Forwarded-Proto: https`）含 HSTS。
- :22/2591 `ssh -Q kex/cipher/mac` 或扫描器复测 → 无 `diffie-hellman-*`、无 hmac-sha1/umac-64、无 chacha20-poly1305。
- 631/111 → 端口关闭或仅本机可达。
