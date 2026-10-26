"""Standalone durable PostgreSQL worker. Run with python -m app.worker."""
import argparse
import asyncio
import json
import logging
import os
from uuid import uuid4
from sqlalchemy import select,func
from app.db.session import AsyncSessionLocal,engine
from app.models.operations import WorkerHeartbeat
from app.services.operations import upsert,utcnow,aware
from app.settings import get_settings

log=logging.getLogger('worker')


async def health():
    table=WorkerHeartbeat.__table__
    async with AsyncSessionLocal() as db:
        latest=await db.scalar(select(func.max(table.c.seen_at)).where(table.c.id==os.uname().nodename))
    return bool(latest and (utcnow()-aware(latest)).total_seconds()<60)


async def run():
    from app.services.jobs import run_one
    settings=get_settings();identity=os.uname().nodename
    while True:
        try:
            async with AsyncSessionLocal() as db:
                await db.execute(upsert(db,WorkerHeartbeat).values(id=identity,seen_at=utcnow()).on_conflict_do_update(
                    index_elements=[WorkerHeartbeat.id],set_={'seen_at':utcnow()}))
                await db.commit()
            if not await run_one(AsyncSessionLocal,settings):
                from app.services.maintenance import maintain
                await maintain(AsyncSessionLocal)
                await asyncio.sleep(settings.worker_poll_seconds)
        except Exception as exc:
            log.error(json.dumps({'event':'worker_loop_error','type':type(exc).__name__}))
            await asyncio.sleep(settings.worker_poll_seconds)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--health',action='store_true');args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(message)s')
    try:
        if args.health:raise SystemExit(0 if asyncio.run(health()) else 1)
        asyncio.run(run())
    finally:asyncio.run(engine.dispose())

if __name__=='__main__':main()
