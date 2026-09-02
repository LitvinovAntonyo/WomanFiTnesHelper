#!/usr/bin/env bash
set -euo pipefail

output="${1:-running-services.txt}"
systemctl list-units --type=service --state=running --no-pager --no-legend \
  | awk '{print $1}' \
  | sort > "$output"
printf 'Saved %s running services to %s\n' "$(wc -l < "$output" | tr -d ' ')" "$output"
