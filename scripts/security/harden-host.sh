#!/usr/bin/env bash
#
# zw-brain 宿主安全加固（漏扫报告 0609 Layer 2）
# ────────────────────────────────────────────────────────────────────────────
# 整改对象：被扫 VM 宿主机（非 zw-brain 容器本身）上的 OS 级发现：
#   - SSH 弱 DHE KEX (D(HE)ater)、弱 MAC、Terrapin (CVE-2023-48795)
#   - CUPS 打印服务 (631)、RPC portmapper / rpcbind (111) 对外暴露
#   - ICMP timestamp 信息泄漏
# 不在本脚本处理：CPython DoS（属镜像重建，见 docs/deployment/security-hardening-0609.md）、
#                  TCP timestamps（默认保留，关闭伤 PAWS/性能，低危，见 runbook 接受风险）。
#
# 安全纪律（对齐 ~/.claude/CLAUDE.md 破坏性命令约束）：
#   - 默认 DRY-RUN：只打印将做什么，绝不改动系统。必须显式 --apply 才执行。
#   - 每个被改文件先备份为 <file>.zw-bak-<时间戳>。
#   - 幂等：重复运行结果一致（drop-in 配置覆盖写、服务已停则跳过）。
#   - 改完自检：reload 前 sshd -t 校验；结尾汇总最终姿态。
#
# 用法：
#   sudo bash scripts/security/harden-host.sh            # DRY-RUN，先看清单
#   sudo bash scripts/security/harden-host.sh --apply    # 审阅 dry-run 后真正执行
#   sudo bash scripts/security/harden-host.sh --apply --keep-cups   # 保留 CUPS（仅本机确需打印时）
#
set -euo pipefail

APPLY=0
KEEP_CUPS=0
KEEP_RPCBIND=0
HARDEN_FAILED=0   # 任一步骤失败（含生效值断言）置 1 → 脚本整体退出非零，绝不假报成功
TS="$(date +%Y%m%d-%H%M%S)"
SSHD_DROPIN="/etc/ssh/sshd_config.d/50-zw-brain-hardening.conf"

for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;;
    --keep-cups) KEEP_CUPS=1 ;;
    --keep-rpcbind) KEEP_RPCBIND=1 ;;
    -h|--help) grep -E '^# ' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "未知参数：${arg}（见 --help）" >&2; exit 2 ;;
  esac
done

# ── 输出助手 ────────────────────────────────────────────────────────────────
c_step() { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
c_do()   { printf '   \033[32m✓\033[0m %s\n' "$*"; }
c_dry()  { printf '   \033[33m[dry-run]\033[0m %s\n' "$*"; }
c_warn() { printf '   \033[33m!\033[0m %s\n' "$*"; }
c_skip() { printf '   - %s\n' "$*"; }

if [ "$APPLY" -eq 1 ]; then
  [ "$(id -u)" -eq 0 ] || { echo "--apply 需要 root（请用 sudo）" >&2; exit 2; }
  printf '\033[1;31m*** APPLY 模式：将真正修改本机配置 ***\033[0m\n'
else
  printf '\033[1mDRY-RUN 模式：不会改动任何东西。审阅后加 --apply 执行。\033[0m\n'
fi

have() { command -v "$1" >/dev/null 2>&1; }
HAS_SYSTEMD=0; have systemctl && HAS_SYSTEMD=1

backup() {
  local path="$1"
  [ -f "$path" ] || return 0
  local b="${path}.zw-bak-${TS}"
  if [ "$APPLY" -eq 1 ]; then cp -p "$path" "$b"; c_do "备份 $path -> $b"
  else c_dry "备份 $path -> $b"; fi
}

# 把 stdin 内容写入文件（apply）或预览（dry-run）；写前自动备份既有文件。
write_file() {
  local path="$1"; local content; content="$(cat)"
  if [ "$APPLY" -eq 1 ]; then
    backup "$path"; mkdir -p "$(dirname "$path")"
    printf '%s\n' "$content" > "$path"; c_do "写入 $path"
  else
    c_dry "将写入 ${path}："
    printf '%s\n' "$content" | sed 's/^/        | /'
  fi
}

run() {  # 执行（apply）或预览（dry-run）一条命令
  if [ "$APPLY" -eq 1 ]; then c_do "$*"; "$@"
  else c_dry "$*"; fi
}

# ── 1. SSH 加固（D(HE)ater / 弱 MAC / Terrapin）─────────────────────────────
harden_sshd() {
  c_step "SSH 加固 — 去弱 KEX/MAC，缓解 Terrapin"
  if ! have sshd && [ ! -f /etc/ssh/sshd_config ]; then
    c_skip "未发现 sshd / sshd_config，跳过。"; return 0
  fi
  # 仅当主配置 Include 了 sshd_config.d 才用 drop-in；否则回落追加主配置（仍先备份）。
  local use_dropin=0
  if [ -f /etc/ssh/sshd_config ] && grep -qE '^\s*Include\s+/etc/ssh/sshd_config\.d/' /etc/ssh/sshd_config; then
    use_dropin=1
  fi
  # KEX：只留 ECDH/curve25519(+PQC)，去掉全部有限域 diffie-hellman-*（D(HE)ater）与 SHA1 KEX。
  # Ciphers：GCM+CTR，去掉 chacha20-poly1305（Terrapin 在 <9.6 无 strict-kex 时的配置级缓解）。
  # MACs：仅 ETM 的 sha2/umac-128，去掉 hmac-sha1 / umac-64 / md5（弱 MAC）。
  local conf
  conf="$(cat <<'EOF'
# zw-brain 宿主加固（漏扫 0609）。删除本文件并 reload sshd 即可回滚。
# Terrapin 的彻底修复是升级 OpenSSH>=9.6（启用 strict-kex）；下列算法收紧是 <9.6 的配置级缓解。
KexAlgorithms sntrup761x25519-sha512@openssh.com,curve25519-sha256,curve25519-sha256@libssh.org
Ciphers aes256-gcm@openssh.com,aes128-gcm@openssh.com,aes256-ctr,aes192-ctr,aes128-ctr
MACs hmac-sha2-256-etm@openssh.com,hmac-sha2-512-etm@openssh.com,umac-128-etm@openssh.com
EOF
)"
  if [ "$use_dropin" -eq 1 ]; then
    printf '%s\n' "$conf" | write_file "$SSHD_DROPIN"
  else
    c_warn "sshd_config 未 Include sshd_config.d，将把加固块追加进主配置（先备份）。"
    if [ "$APPLY" -eq 1 ]; then
      backup /etc/ssh/sshd_config
      # 幂等：先删旧的本工具块，再追加。
      sed -i '/# >>> zw-brain harden 0609/,/# <<< zw-brain harden 0609/d' /etc/ssh/sshd_config
      { echo "# >>> zw-brain harden 0609"; printf '%s\n' "$conf"; echo "# <<< zw-brain harden 0609"; } >> /etc/ssh/sshd_config
      c_do "追加加固块到 /etc/ssh/sshd_config"
    else
      c_dry "将追加加固块到 /etc/ssh/sshd_config（含 >>> zw-brain harden 0609 <<< 标记，便于回滚）"
    fi
  fi
  # 校验后 reload —— sshd -t 失败绝不 reload，且**自动回滚本次写入**：否则坏配置留在盘上，
  # 当下不 reload 看似无事，但下一次 sshd 重启会因坏配置失败 → 把自己锁在门外（lockout footgun）。
  if [ "$APPLY" -eq 1 ]; then
    if sshd -t; then
      c_do "sshd -t 通过"
      if [ "$HAS_SYSTEMD" -eq 1 ]; then systemctl reload ssh 2>/dev/null || systemctl reload sshd 2>/dev/null || c_warn "reload 失败，请手动 systemctl reload ssh"
      else service ssh reload 2>/dev/null || service sshd reload 2>/dev/null || c_warn "reload 失败，请手动 reload sshd"; fi
      assert_sshd_algos || return 1
    else
      # 回滚本次刚写入的内容，确保下次 sshd 重启不会被坏配置阻断（算法名在旧 sshd 上可能不识别）。
      if [ "$use_dropin" -eq 1 ]; then
        rm -f "$SSHD_DROPIN"; c_warn "sshd -t 校验失败！已删除刚写入的 $SSHD_DROPIN（回滚），未 reload。"
      else
        sed -i '/# >>> zw-brain harden 0609/,/# <<< zw-brain harden 0609/d' /etc/ssh/sshd_config
        c_warn "sshd -t 校验失败！已从 sshd_config 移除刚追加的加固块（回滚），未 reload。"
      fi
      c_warn "原配置（含算法收紧）未生效；请人工评估该 sshd 版本支持的算法后再试。"; return 1
    fi
  else
    c_dry "sshd -t 校验通过后 reload ssh（失败则自动回滚本次写入，绝不留坏配置）"
  fi
}

# 生效值硬断言 —— 写入成功 ≠ 生效。OpenSSH 对同一指令取**首个出现值**：主配置或
# 字典序更早的 drop-in 里既有的 KexAlgorithms/Ciphers/MACs 行会让本脚本的收紧静默落空
# （0610 复扫 .126 即此症状：KEX 变了但 Ciphers/MACs 原样、Terrapin/弱 MAC 仍在）。
# 断言失败 → 列出定义了相关指令的全部配置文件 → 返回非零，绝不报"加固完成"。
assert_sshd_algos() {
  # 局限：sshd -T 不展开 Match 块（需 -C 连接参数）——Match 块内另设的弱算法本断言看不见，
  # 由下方"列出定义相关指令的文件"诊断兜底，运维人工核对。
  local eff fail=0
  if ! eff="$(sshd -T 2>/dev/null)"; then
    c_warn "sshd -T 不可用，无法断言生效算法；请人工核对 sshd -T 输出。"; return 1
  fi
  if printf '%s\n' "$eff" | grep -i '^kexalgorithms ' | grep -qE 'diffie-hellman-'; then
    c_warn "生效 KexAlgorithms 仍含 diffie-hellman-*（D(HE)ater 未消除）"; fail=1
  fi
  if printf '%s\n' "$eff" | grep -i '^ciphers ' | grep -q 'chacha20-poly1305'; then
    c_warn "生效 Ciphers 仍含 chacha20-poly1305（Terrapin 缓解未生效）"; fail=1
  fi
  if printf '%s\n' "$eff" | grep -i '^macs ' | grep -qE 'umac-64|hmac-sha1|hmac-md5'; then
    c_warn "生效 MACs 仍含弱算法（umac-64 / hmac-sha1 / md5）"; fail=1
  fi
  if [ "$fail" -eq 1 ]; then
    c_warn "断言失败：本脚本写入的值被更早出现的配置覆盖。定义了相关指令的文件："
    grep -rilE '^[[:space:]]*(KexAlgorithms|Ciphers|MACs)[[:space:]]' \
      /etc/ssh/sshd_config /etc/ssh/sshd_config.d/ 2>/dev/null | sed 's/^/        /' || true
    c_warn "OpenSSH 取首个出现值：请删除/收编上述文件中更早的弱算法行后重跑本脚本。"
    return 1
  fi
  c_do "生效算法断言通过（无 diffie-hellman-* / chacha20-poly1305 / 弱 MAC）"
}

# ── 2. 关停不需要的服务（CUPS / rpcbind）─────────────────────────────────────
disable_unit() {
  local unit="$1"
  if [ "$HAS_SYSTEMD" -eq 1 ] && systemctl list-unit-files 2>/dev/null | grep -q "^${unit}"; then
    run systemctl disable --now "$unit"
    run systemctl mask "$unit"
  else
    c_skip "$unit 未安装/无 systemd，跳过。"
  fi
}

disable_services() {
  c_step "关停产品不需要的对外服务"
  if [ "$KEEP_CUPS" -eq 1 ]; then
    c_warn "--keep-cups：保留 CUPS。请改用防火墙仅放行本机：iptables -A INPUT -p tcp --dport 631 ! -s 127.0.0.1 -j DROP"
  else
    # cups.path 会在打印队列出现时把 cups.service 拉起来，必须一并关停。
    disable_unit "cups.service"; disable_unit "cups.socket"; disable_unit "cups.path"; disable_unit "cups-browsed.service"
  fi
  if [ "$KEEP_RPCBIND" -eq 1 ]; then
    c_warn "--keep-rpcbind：保留 rpcbind（NFS 需要）。请用防火墙限制 111/tcp,udp 源地址。"
  else
    disable_unit "rpcbind.service"; disable_unit "rpcbind.socket"
  fi
}

# ── 3. ICMP timestamp 信息泄漏（防火墙丢弃 type 13/14）──────────────────────
harden_icmp_timestamp() {
  c_step "屏蔽 ICMP timestamp（type 13 请求 / 14 回复）"
  if have nft; then
    if [ "$APPLY" -eq 1 ]; then
      nft list table inet zw_brain_harden >/dev/null 2>&1 || run nft add table inet zw_brain_harden
      run nft 'add chain inet zw_brain_harden input { type filter hook input priority -10 ; }'
      run nft add rule inet zw_brain_harden input icmp type timestamp-request drop
      run nft add rule inet zw_brain_harden input icmp type timestamp-reply drop
      c_warn "nft 运行时规则非持久化：重启即失效。请固化进 /etc/nftables.conf（或发行版防火墙服务）并确认 nftables.service 开机启用。"
    else
      c_dry "nft：新建 inet zw_brain_harden 表/链，drop icmp timestamp-request/-reply"
    fi
  elif have iptables; then
    add_ipt() { iptables -C "$@" 2>/dev/null || iptables -A "$@"; }  # 幂等
    if [ "$APPLY" -eq 1 ]; then
      add_ipt INPUT -p icmp --icmp-type timestamp-request -j DROP && c_do "iptables drop timestamp-request"
      add_ipt INPUT -p icmp --icmp-type timestamp-reply -j DROP && c_do "iptables drop timestamp-reply"
      c_warn "iptables 规则非持久化：请用 iptables-save 或防火墙服务固化。"
    else
      c_dry "iptables -A INPUT -p icmp --icmp-type timestamp-request/-reply -j DROP（幂等检查后追加）"
    fi
  else
    c_warn "未发现 nft/iptables，跳过 ICMP timestamp 屏蔽（低危 2.1，可在边界防火墙处理）。"
  fi
}

# ── 4. 自检汇总 ──────────────────────────────────────────────────────────────
verify() {
  c_step "自检 — 最终姿态"
  if have sshd; then
    if sshd -T >/dev/null 2>&1; then
      echo "   sshd 生效算法："
      sshd -T 2>/dev/null | grep -iE '^(kexalgorithms|ciphers|macs) ' | sed 's/^/        /'
    else
      c_warn "sshd -T 需 root 且配置有效；dry-run 或非 root 下跳过生效值打印。"
    fi
  fi
  if [ "$HAS_SYSTEMD" -eq 1 ]; then
    for u in cups.service rpcbind.service; do
      if systemctl list-unit-files 2>/dev/null | grep -q "^${u}"; then
        printf '   %s: %s\n' "$u" "$(systemctl is-enabled "$u" 2>/dev/null || echo n/a) / $(systemctl is-active "$u" 2>/dev/null || echo inactive)"
      fi
    done
  fi
  echo
  echo "   提示：CPython DoS(8800) 与 Server banner 属产品层，由镜像重建 + 应用代码修复，"
  echo "        详见 docs/deployment/security-hardening-0609.md。"
}

main() {
  harden_sshd || { HARDEN_FAILED=1; c_warn "SSH 加固中止（见上）。"; }
  disable_services
  harden_icmp_timestamp
  verify
  echo
  if [ "$HARDEN_FAILED" -eq 1 ]; then
    printf '\033[1;31m存在失败项（见上 warn，典型为 sshd 生效值断言未通过）：退出码 1，处理后重跑。\033[0m\n'
    exit 1
  fi
  if [ "$APPLY" -eq 1 ]; then
    printf '\033[1;32m完成。建议从另一终端验证 SSH 仍可登录后再断开当前会话。\033[0m\n'
  else
    printf '\033[1m这是 DRY-RUN。确认无误后加 --apply 执行。\033[0m\n'
  fi
}

main
