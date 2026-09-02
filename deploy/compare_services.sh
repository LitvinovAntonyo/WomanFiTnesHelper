#!/usr/bin/env bash
set -euo pipefail

baseline="${1:?Usage: compare_services.sh BASELINE_FILE}"
current="$(mktemp)"
trap 'rm -f "$current"' EXIT

systemctl list-units --type=service --state=running --no-pager --no-legend \
  | awk '{print $1}' \
  | sort > "$current"

printf 'Services no longer running since baseline:\n'
comm -23 "$baseline" "$current" || true
printf 'Newly running services:\n'
comm -13 "$baseline" "$current" || true
