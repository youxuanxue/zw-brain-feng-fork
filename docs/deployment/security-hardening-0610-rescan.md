# 漏扫复扫核查（0610）

> 源报告：`old/问题反馈/安全扫描报告-0610/`（主机 `100.69.5.126` 24 条 / `100.112.2.125` 48 条）。
> 对照基线：第一轮 `old/问题反馈/安全扫描报告-0609/` + 整改 PR #233（`docs/deployment/security-hardening-0609.md`）。
> 本文回答三个问题：**第一轮整改哪些被复扫实证生效、哪些没生效、剩下的归谁**。

## 0. 一页结论

总发现 87 → 72（.126：28→24；.125：59→48）；每台机各剩 1 条高危，且都是同一条 **OpenSSH 8.9p1 版本匹配类**（8.1）。

1. **产品层（:8800）整改实证生效，本轮无需新代码改动。**
   Python DoS 4 条（1 高危 + 3 中危）与 `Python Detection Consolidation` 全部消失——banner 去版本化 +
   安全头（PR #233）在被扫实例上已生效。:8800 残留 6 条全部为 0.0 信息级指纹
   （方法枚举 / 安全头检测 / banner 枚举 / Services / WAS 汇总），属 0609 手册 #12/#15 既登记的接受项。
   副作用良性：.125 新增 1 条 `Unknown OS and Service Banner Reporting`（info）——banner 藏掉后扫描器
   认不出 OS 了，这正是去版本化的预期效果。
2. **宿主 .125：`harden-host.sh` 大部分生效，唯 CUPS 未关。**
   sshd 收紧 ✓（D(HE)ater 7.5 高危 / Terrapin 5.9 中危 / 弱 MAC 全消失，PQC KEX 仍 Supported——与脚本
   写入的算法集一致）、rpcbind ✓（111 端口 3 条全消）、ICMP timestamp ✓。
   但 **631/tcp CUPS 仍在跑**：19 条原样未动（含 BREACH 5.9 中危 + 自签证书全家桶）。
   推断执行时带了 `--keep-cups`（或事后被解除 mask）且未配套防火墙限源。
3. **宿主 .126：判定未执行（或未完整执行）`harden-host.sh --apply`。**
   证据链：D(HE)ater 消失但 **PQC KEX 反而从 Supported 变 Missing**——脚本的 KexAlgorithms 首项就是
   `sntrup761x25519`，若脚本生效 PQC 不可能 Missing；同时 **Ciphers/MACs 未收紧**（Terrapin 5.9 中危、
   umac-64 弱 MAC 原样在）、ICMP timestamp 仍在。该机的 KEX 像是被人工单独改过（去 DHE 时把 PQC 也去了），
   不是脚本的算法集。
4. **OpenSSH 版本类 10 条/机（含两台共 2 条 8.1 高危）：扫描器纯 banner 版本匹配，不是"未打补丁"的证据。**
   .126 的 Terrapin 报文里扫描器自己看到了 `kex-strict-s-v00@openssh.com`——strict-kex 是 OpenSSH 9.6
   引入、Ubuntu 已 backport 到 8.9p1 的 Terrapin 补丁，**这恰好实证该机的 OpenSSH 在吃发行版安全更新**。
   发行版 backport 不改 banner 版本号，版本匹配类发现在 8.9p1 上永远不会自己消失；出路只有三条：
   OS 大版本升级（队列化）、向扫描方出具 backport 证明做误报豁免、或作为已登记残留接受。
   已登记 `.testing/debt/openssh-version-residual`。

## 1. 0609 → 0610 精确对比

### 1.1 主机 100.112.2.125（59 → 48）

| 类别 | 0609 | 0610 | 判定 |
|---|---|---|---|
| Python DoS（:8800，7.5 高 + 5.5/5.3/5.5 中）×4 + Python Detection | 有 | **消失** | 产品层 banner 去版本化生效 ✅ |
| D(HE)ater（:2591，7.5 高） | 有 | **消失** | 脚本 KEX 收紧生效 ✅ |
| Terrapin（:2591，5.9 中）/ 弱 MAC（2.6 低） | 有 | **消失** | 脚本 Ciphers/MACs 收紧生效 ✅ |
| rpcbind（:111，6.4 中 + 2 info）×3 | 有 | **消失** | 脚本关停 rpcbind 生效 ✅ |
| ICMP Timestamp（2.1 低） | 有 | **消失** | 脚本 nft/iptables 屏蔽生效 ✅ |
| CUPS 全家桶（:631）×19（含 BREACH 5.9 中、自签证书、HSTS/HPKP missing 等） | 有 | **原样残留** | ❌ CUPS 未关停（疑 `--keep-cups` 且未限源） |
| OpenSSH 版本类 ×10（8.1 高 ×1 + 中 ×6 + 低 ×2 + CVE-2016-20012 中） | 有 | 残留 | 版本匹配类，见 §2.3 |
| TCP Timestamps（2.6 低） | 有 | 残留 | 0609 手册 #14 既登记接受 |
| :8800 信息级指纹 ×6 | 有 | 残留 | 0609 手册 #12/#15 接受（info） |
| Unknown OS and Service Banner Reporting（info） | 无 | **新增** | banner 藏掉的良性副作用 |

### 1.2 主机 100.69.5.126（28 → 24）

| 类别 | 0609 | 0610 | 判定 |
|---|---|---|---|
| D(HE)ater（:22，7.5 高） | 有 | **消失** | KEX 已被收紧（但非脚本算法集，见下行） |
| PQC KEX（info） | Supported | **Missing** | ⚠️ 与脚本生效矛盾——脚本 KEX 首项即 sntrup761；判定该机 KEX 系人工单改 |
| Terrapin（:22，5.9 中） | 有 | **原样残留** | ❌ Ciphers 未收紧（chacha20-poly1305 仍启用） |
| 弱 MAC umac-64（2.6 低） | 有 | **原样残留** | ❌ MACs 未收紧 |
| ICMP Timestamp（2.1 低） | 有 | **原样残留** | ❌ 屏蔽未做 |
| rpcbind（:111，6.4 中 + 2 info）×3 | 有 | **消失** | rpcbind 已关 ✅ |
| OpenSSH 版本类 ×10（8.1 高 ×1 + 中 ×6 + 低 ×2 + CVE-2016-20012 中） | 有 | 残留 | 版本匹配类，见 §2.3；Terrapin 报文中 strict-kex 在场 = backport 实证 |
| TCP Timestamps（2.6 低） | 有 | 残留 | 既登记接受 |

## 2. 残留 → 行动清单

### 2.1 主机 .125 — 关停 CUPS（消 19 条，含本机最后一条非版本类中危 BREACH）

```bash
# 不带 --keep-cups 重跑；若该机确需打印，必须配套防火墙限源（脚本会给出规则）
sudo bash scripts/security/harden-host.sh --apply
```

### 2.2 主机 .126 — 完整执行加固脚本（消 Terrapin / 弱 MAC / ICMP / PQC-Missing 共 4 条）

```bash
sudo bash scripts/security/harden-host.sh          # 先 dry-run 审阅
sudo bash scripts/security/harden-host.sh --apply  # 另开终端确认 SSH 可登录后再断开
```

脚本已补强（本 PR）：apply 后用 `sshd -T` **断言生效算法**——写入成功 ≠ 生效，OpenSSH 取首个出现值，
更早的 drop-in / 主配置行会让收紧静默落空（.126 本轮即此症状）；断言失败时退出非零并列出定义了
KexAlgorithms/Ciphers/MACs 的全部配置文件，指给运维清理。

### 2.3 两台机 — OpenSSH 版本类（含 2 条 8.1 高危）

版本匹配类发现升级 `openssh-server` 包**不会清除**（发行版 backport 不抬 banner 版本号）。三选一，
决策归运维/安全双方：

1. **误报豁免**（推荐先做）：向扫描方出具发行版 backport 证明（`apt changelog openssh-server` 中的
   CVE 条目 + 本报告 strict-kex 在场实证），将版本匹配类列入豁免清单。
2. **OS 升级队列**：随宿主 OS 大版本升级（如 Ubuntu 22.04→24.04，OpenSSH ≥9.6）自然清零。
3. **接受残留**：已登记 `.testing/debt/openssh-version-residual.debt.yaml`，触发条件见债条目。

仍应执行的常规动作（不解决版本匹配，但保持补丁水位）：

```bash
sudo apt-get update && sudo apt-get install --only-upgrade openssh-server   # Debian/Ubuntu
```

### 2.4 无需动作

- **:8800 信息级 ×6**：接受（0609 手册 #12/#15）。
- **TCP Timestamps（两机）**：接受（0609 手册 #14，关闭伤 PAWS/性能）。

## 3. 复扫验收口径（第三轮）

- .125:631 → 端口关闭（CUPS 19 条 + BREACH 消失）。
- .126:22 → `ssh -Q` / 复扫无 chacha20-poly1305、无 umac-64、PQC KEX 回到 Supported；ICMP timestamp 无回复。
- 两机非版本类中危清零；版本类按 §2.3 选定路径处置并在扫描方留痕。
- 预期第三轮残留 = OpenSSH 版本类（若未豁免/升级）+ TCP timestamps + 信息级指纹，且均有登记出处。
