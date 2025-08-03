# app/deps/scheduler.py
try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
except Exception:  # pragma: no cover - optional dependency
    class AsyncIOScheduler:  # minimal stub
        def __init__(self, *a, **k):
            self.running = False
        def start(self):
            self.running = True
        def shutdown(self):
            self.running = False

scheduler = AsyncIOScheduler(timezone="America/Detroit")

def start():
    if not scheduler.running:
        scheduler.start()

def shutdown():
    if scheduler.running:
        scheduler.shutdown()
