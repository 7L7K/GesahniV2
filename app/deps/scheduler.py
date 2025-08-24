# app/deps/scheduler.py
from datetime import UTC, datetime, timedelta

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
except Exception:  # pragma: no cover - optional dependency

    class AsyncIOScheduler:  # minimal stub
        def __init__(self, *a, **k):
            self.running = False
            self._jobs = {}

        def start(self):
            self.running = True
            return None  # Explicitly return None to avoid confusion

        async def astart(self):
            """Async version of start for compatibility."""
            return self.start()

        def add_job(
            self,
            func,
            trigger=None,
            id=None,
            args=None,
            replace_existing=False,
            **kwargs,
        ):
            # Best-effort no-op store to satisfy callers
            if id is None:
                id = str(len(self._jobs) + 1)
            if not replace_existing and id in self._jobs:
                return self._jobs[id]
            self._jobs[id] = {
                "func": func,
                "trigger": trigger,
                "args": args or [],
                "kwargs": kwargs,
            }
            return self._jobs[id]

        def remove_job(self, id):
            self._jobs.pop(id, None)

        def get_job(self, id):
            return self._jobs.get(id)

        def shutdown(self):
            self._jobs.clear()
            self.running = False


_base_scheduler = AsyncIOScheduler(timezone="America/Detroit")


class _CompatScheduler:
    """Thin wrapper to provide a v3-compatible ``add_job`` on v4 schedulers.

    - If the underlying has ``add_job``, delegate directly (APScheduler v3)
    - Else, translate ``trigger="interval|cron|date"`` kwargs into v4 Trigger
      objects and call ``schedule``/``add_schedule`` if available
    - Else, store in-memory as a no-op (tests/dev without APScheduler)
    """

    def __init__(self, impl):
        self._impl = impl
        self._jobs = {}

    def __getattr__(self, name):
        return getattr(self._impl, name)

    @property
    def running(self):
        return getattr(self._impl, "running", False)

    def start(self):
        return self._impl.start()

    def shutdown(self, *a, **k):
        return self._impl.shutdown(*a, **k)

    def add_job(
        self, func, trigger=None, id=None, args=None, replace_existing=False, **kwargs
    ):
        # v3 path
        if hasattr(self._impl, "add_job"):
            return self._impl.add_job(
                func,
                trigger,
                id=id,
                args=args,
                replace_existing=replace_existing,
                **kwargs,
            )

        # v4 path: build Trigger object
        trig_obj = None
        kind = trigger if isinstance(trigger, str) else None
        try:
            if kind == "cron":
                from apscheduler.triggers.cron import CronTrigger

                trig_obj = CronTrigger(**kwargs)
                kwargs = {}
            elif kind == "interval":
                from apscheduler.triggers.interval import IntervalTrigger

                trig_obj = IntervalTrigger(**kwargs)
                kwargs = {}
            elif kind == "date":
                from apscheduler.triggers.date import DateTrigger as _DateTrigger

                run_date = kwargs.pop("run_date", None)
                seconds = kwargs.pop("seconds", None)
                if run_date is None and seconds is not None:
                    run_date = datetime.now(UTC) + timedelta(seconds=seconds)
                trig_obj = (
                    _DateTrigger(run_date=run_date) if run_date is not None else None
                )
        except Exception:
            trig_obj = None

        schedule_fn = getattr(self._impl, "add_schedule", None) or getattr(
            self._impl, "schedule", None
        )
        if trig_obj is not None and schedule_fn is not None:
            return schedule_fn(
                func,
                trig_obj,
                args=args or [],
                id=id,
                replace_existing=replace_existing,
            )

        # Fallback: in-memory store only
        key = id or str(len(self._jobs) + 1)
        if not replace_existing and key in self._jobs:
            return self._jobs[key]
        self._jobs[key] = {
            "func": func,
            "trigger": trigger,
            "args": args or [],
            "kwargs": kwargs,
        }
        return self._jobs[key]

    def remove_job(self, id):
        if hasattr(self._impl, "remove_job"):
            try:
                return self._impl.remove_job(id)
            except Exception:
                pass
        self._jobs.pop(id, None)

    def get_job(self, id):
        if hasattr(self._impl, "get_job"):
            try:
                return self._impl.get_job(id)
            except Exception:
                pass
        return self._jobs.get(id)


scheduler = _CompatScheduler(_base_scheduler)


def start():
    if not scheduler.running:
        scheduler.start()


def shutdown():
    if scheduler.running:
        scheduler.shutdown()
