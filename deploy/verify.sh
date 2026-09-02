#!/usr/bin/env bash
set -euo pipefail

systemctl is-enabled fitness-bot.service
systemctl is-active fitness-bot.service
systemctl status fitness-bot.service --no-pager --lines=20
journalctl -u fitness-bot.service --since '-10 minutes' --no-pager --lines=100

set -a
source /etc/fitness-bot/fitness-bot.env
set +a
cd /opt/fitness-bot
/opt/fitness-bot/.venv/bin/python - <<'PY'
import asyncio
from app.config import load_settings
from app.database import Database

async def check():
    settings = load_settings()
    db = Database(settings)
    ok = await db.healthcheck()
    await db.close()
    if not ok:
        raise SystemExit('Database healthcheck failed')
    print('Database healthcheck: OK')

asyncio.run(check())
PY
