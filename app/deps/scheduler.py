# app/deps/scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler(timezone="America/Detroit")

def start():
    if not scheduler.running:
        scheduler.start()

def shutdown():
    if scheduler.running:
        scheduler.shutdown()
