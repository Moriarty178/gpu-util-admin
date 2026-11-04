#!/bin/sh
# Chạy trước mọi lệnh của container api: nâng cấp schema + seed (cả 2 idempotent), rồi exec lệnh chính.
set -eu
cd /srv/backend
alembic upgrade head
python -m app.db.seed
exec "$@"
