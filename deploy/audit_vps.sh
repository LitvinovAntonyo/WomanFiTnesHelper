#!/usr/bin/env bash
set -euo pipefail

section() {
  printf '\n## %s\n' "$1"
}

section "Timestamp"
date --iso-8601=seconds

section "OS and kernel"
if command -v hostnamectl >/dev/null 2>&1; then hostnamectl
else uname -a
fi
if [[ -r /etc/os-release ]]; then sed -n '1,20p' /etc/os-release; fi

section "CPU"
if command -v lscpu >/dev/null 2>&1; then lscpu
else getconf _NPROCESSORS_ONLN
fi

section "RAM and swap"
free -h
if command -v swapon >/dev/null 2>&1; then swapon --show; fi

section "Disk"
df -hT / /opt /var 2>/dev/null || df -hT /

section "Load"
uptime
ps -eo pid,comm,%cpu,%mem --sort=-%cpu | head -n 16

section "Python"
command -v python3 || true
python3 --version 2>&1 || true

section "Running systemd services"
systemctl list-units --type=service --state=running --no-pager --no-legend

section "Failed systemd services"
systemctl list-units --type=service --state=failed --no-pager --no-legend

section "Listening sockets"
if command -v ss >/dev/null 2>&1; then ss -lntup
elif command -v netstat >/dev/null 2>&1; then netstat -lntup
fi

section "Existing bot-like processes"
ps -eo user,pid,etimes,comm | grep -Ei 'python|telegram|bot|parser' | grep -v grep || true
