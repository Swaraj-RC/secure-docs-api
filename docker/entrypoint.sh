#!/bin/bash
set -e

echo "==> Waiting for database..."
MAX_RETRIES=30
RETRY_COUNT=0
until python -c "
import asyncio, asyncpg, os
async def check():
    url = os.environ.get('DATABASE_URL', '').replace('+asyncpg', '')
    conn = await asyncpg.connect(url.replace('postgresql+asyncpg', 'postgresql'))
    await conn.close()
asyncio.run(check())
" 2>/dev/null; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
        echo "==> ERROR: Database not available after $MAX_RETRIES attempts"
        exit 1
    fi
    echo "==> Database not ready (attempt $RETRY_COUNT/$MAX_RETRIES), waiting..."
    sleep 2
done
echo "==> Database is ready!"

echo "==> Running database migrations..."
alembic upgrade head

echo "==> Starting application server..."
exec uvicorn app.main:app \
    --host "${HOST:-0.0.0.0}" \
    --port "${PORT:-8000}" \
    --workers "${WORKERS:-1}" \
    --access-log
