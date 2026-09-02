#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  printf 'Run as root: sudo %s PROJECT_SOURCE [ENV_FILE]\n' "$0" >&2
  exit 1
fi

source_dir="${1:?Usage: install.sh PROJECT_SOURCE [ENV_FILE]}"
env_source="${2:-}"
install_dir="/opt/fitness-bot"
config_dir="/etc/fitness-bot"
env_target="${config_dir}/fitness-bot.env"
service_target="/etc/systemd/system/fitness-bot.service"

if [[ ! -f "${source_dir}/requirements.txt" || ! -d "${source_dir}/app" ]]; then
  printf 'PROJECT_SOURCE does not look like the fitness bot project: %s\n' "$source_dir" >&2
  exit 1
fi

python3 - <<'PY'
import sys
if not ((3, 10) <= sys.version_info[:2] < (3, 15)):
    raise SystemExit(f"Python 3.10-3.14 is required, found {sys.version.split()[0]}")
PY

if ! id fitnessbot >/dev/null 2>&1; then
  useradd --system --home-dir /nonexistent --shell /usr/sbin/nologin fitnessbot
fi

install -d -o root -g fitnessbot -m 0750 "$install_dir" "$config_dir"
install -d -o fitnessbot -g fitnessbot -m 0700 /var/lib/fitness-bot

cp -a "${source_dir}/app" "$install_dir/"
cp -a "${source_dir}/requirements.txt" "${source_dir}/pyproject.toml" "$install_dir/"
chown -R root:fitnessbot "$install_dir/app" "$install_dir/requirements.txt" "$install_dir/pyproject.toml"
chmod -R go-w "$install_dir/app" "$install_dir/requirements.txt" "$install_dir/pyproject.toml"

if [[ ! -x "${install_dir}/.venv/bin/python" ]]; then
  python3 -m venv "${install_dir}/.venv"
fi
"${install_dir}/.venv/bin/python" -m pip install --disable-pip-version-check --upgrade pip
"${install_dir}/.venv/bin/pip" install --disable-pip-version-check -r "${install_dir}/requirements.txt"
chown -R root:fitnessbot "${install_dir}/.venv"
chmod -R go-w "${install_dir}/.venv"

if [[ -n "$env_source" ]]; then
  install -o root -g fitnessbot -m 0640 "$env_source" "$env_target"
elif [[ ! -f "$env_target" ]]; then
  install -o root -g fitnessbot -m 0640 "${source_dir}/deploy/fitness-bot.env.example" "$env_target"
  printf 'Created %s from the example. Fill it locally on the VPS, then rerun this command.\n' "$env_target" >&2
  exit 2
fi

if ! grep -Eq '^TELEGRAM_BOT_TOKEN=.+$' "$env_target"; then
  printf 'TELEGRAM_BOT_TOKEN is empty in %s\n' "$env_target" >&2
  exit 2
fi

install -o root -g root -m 0644 "${source_dir}/deploy/fitness-bot.service" "$service_target"
systemctl daemon-reload
systemctl enable --now fitness-bot.service
systemctl is-active --quiet fitness-bot.service
printf 'fitness-bot.service is active. Existing services were not stopped or restarted.\n'
