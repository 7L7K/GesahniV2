import os
import datetime as dt
import subprocess
import sys
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.models import (
    Base,
    AuthUser,
    Resident,
    CareDevice,
    Alert,
    AlertEvent,
    MusicPreferences,
)

DB_URL = os.getenv("DATABASE_URL", "postgresql://app:app_pw@localhost:5432/gesahni").replace("postgresql://", "postgresql+psycopg2://")
engine = create_engine(DB_URL, future=True)

def run_database_smoke_tests():
    """Run Phase 5 database behavior smoke tests."""
    print("🚀 Running Phase 5 Database Behavior Smoke Tests...")

    try:
        # Run the pytest smoke tests for Phase 5
        result = subprocess.run([
            sys.executable, "-m", "pytest",
            "tests/smoke/test_phase5_database_behavior.py",
            "-v", "--tb=short"
        ], capture_output=True, text=True, cwd=os.path.dirname(__file__))

        if result.returncode == 0:
            print("✅ Phase 5 Database Behavior Smoke Tests PASSED")
            return True
        else:
            print("❌ Phase 5 Database Behavior Smoke Tests FAILED")
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)
            return False

    except Exception as e:
        print(f"❌ Error running Phase 5 smoke tests: {e}")
        return False


def main():
    print("🔍 Running Basic Database Smoke Tests...")

    with Session(engine, future=True) as s:
        # Create a user (auth)
        u = AuthUser(email="test@example.com", name="Test User")
        s.add(u)
        s.flush()  # u.id available

        # Music prefs row (music -> auth FK)
        mp = MusicPreferences(user_id=u.id, default_provider="spotify")
        s.add(mp)

        # Create a resident (care)
        r = Resident(name="Alice")
        s.add(r)
        s.flush()

        # Link a device to resident (care -> care FK)
        d = CareDevice(resident_id=r.id, battery_pct=88)
        s.add(d)

        # Create an alert and an event with JSONB meta
        a = Alert(resident_id=r.id, kind="battery_low", severity="low", status="open", created_at=dt.datetime.now(dt.timezone.utc))
        s.add(a)
        s.flush()
        ev = AlertEvent(alert_id=a.id, type="notified", meta={"threshold": 20, "battery_pct": 18})
        s.add(ev)

        s.commit()

    with Session(engine, future=True) as s:
        # Read back and join across schemas
        q = s.execute(
            select(Resident.name, CareDevice.battery_pct)
            .join(CareDevice, CareDevice.resident_id == Resident.id)
        ).all()
        print("✅ Resident + Device battery:", q)

        q2 = s.execute(select(MusicPreferences).limit(1)).scalars().all()
        print("✅ Music preferences rows:", len(q2))

    print("✅ Basic Database Smoke Tests PASSED")

    # Run Phase 5 database behavior tests
    print()
    success = run_database_smoke_tests()

    if success:
        print("\n🎉 ALL SMOKE TESTS PASSED!")
        return 0
    else:
        print("\n❌ SOME SMOKE TESTS FAILED!")
        return 1

if __name__ == "__main__":
    sys.exit(main())