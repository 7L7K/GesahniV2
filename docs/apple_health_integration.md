# Gesahni Health Relay – Integration Plan

This document outlines the full plan for integrating Apple Watch + iOS HealthKit data into Gesahni.
The goal: create a **"constant watch" caregiving system** that ingests Mom's health/activity data, stores it in Gesahni, and surfaces it through a **Today Card, alerts, and automations**.

---

## Why This Path
- **Gold-standard data quality**: Apple Watch + HealthKit is the canonical source of health data.
- **Background delivery**: Near real-time updates (5–15 min) without manual intervention.
- **Rich signals**: Heart, activity, sleep, mobility, oxygen, HRV, noise exposure, location, motion state.
- **Actionable caregiving**: Gesahni adds automation, alerts, and AI summaries on top of raw metrics.
- **Privacy & trust**: Granular consent, opt-out switch, transparent logs.

---

## Architecture Overview

Apple Watch → iPhone Health (HealthKit) → Gesahni Health Relay (iOS App)
↳ HKObserverQuery + AnchoredObjectQuery (background delivery)
↳ CoreMotion + Location significant-change updates
↳ WatchConnectivity (optional) for battery + Live Check-In
↳ Secure POST → Gesahni /v1/healthkit/ingest → TimescaleDB

- **iOS Relay App**: SwiftUI + HealthKit + Motion + Location + Networking.
- **Optional Watch App**: battery % reporting + Live Check-In workout session.
- **Backend**: FastAPI endpoint + Postgres/TimescaleDB table.
- **Frontend**: Today Card (Next.js) + alert banners.

---

## Data Sources

### HealthKit (Quantities & Categories)
- Heart Rate (live & resting)
- Heart Rate Variability (SDNN)
- VO₂ Max
- Steps, Distance, Flights
- Walking Speed, Walking HR Average
- Mobility Metrics (steadiness, gait, 6-min walk)
- Sleep Analysis (stages, duration)
- Blood Oxygen (Series 6+)
- Environmental Noise, Headphone Audio Exposure
- ECG classification + waveform (if available)
- Irregular Rhythm Notifications
- Medication logs (if used)

### CoreMotion
- Activity state: `stationary | walking | running | automotive`

### Location
- Significant change updates
- Home/away geofence

### Watch App (optional)
- Watch battery %
- Triggered Live Check-In: 10-min workout session → near real-time HR stream

---

## Backend (GesahniV2)

### Table
```sql
CREATE TABLE hk_samples (
  user_id TEXT NOT NULL,
  device  TEXT NOT NULL,
  type    TEXT NOT NULL,
  t_start TIMESTAMPTZ NOT NULL,
  t_end   TIMESTAMPTZ NOT NULL,
  value_text TEXT,
  value_num DOUBLE PRECISION,
  inserted_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX hk_idx ON hk_samples (user_id, type, t_start DESC);
Endpoint
POST /v1/healthkit/ingest
Auth: require_user, whitelist mom's user_id.
Input: { device_label, samples[] }
Each sample: { type, start, end, value }
Writes to hk_samples.
Summary Endpoint
GET /v1/health/summary?user=mom
Returns:

{
  "latest_hr": 84,
  "rest_hr": 65,
  "hrv": 42,
  "steps_today": 3200,
  "sleep_last_night": "7h 45m",
  "motion_state": "walking",
  "at_home": true,
  "watch_battery": 76,
  "last_sync": "2025-08-25T14:32:00Z"
}
Alerts
Start with 3 rules:
Heart spike: HR > 115 bpm for ≥5 minutes → notify King.
Low steps: <1000 steps by 3pm and motion_state != walking → gentle nudge on TV/phone.
Low battery: watch battery <20% → banner + ping.
Future rules:
Resting HR ↑ >10% vs baseline
HRV ↓ >15% vs baseline
No steps all day
Sleep < 5 hours
Frontend – Today Card
One clean card in Next.js, mirrored to TV:
Latest HR + resting HR + HRV
Steps today (progress ring)
Sleep last night (total + stages)
Current motion state
Home/away
Watch battery %
Last sync timestamp
"Start Live Check-In" button (if watch app present)
Build Order (Recommended)
Phase 1 – Backend foundation
✅ Finish move to VECTOR_DSN
✅ Create hk_samples table + index
✅ Implement /v1/healthkit/ingest
✅ Add ingest metrics (HK_SAMPLES_INGESTED, ingest lag histogram)
✅ Auth hardening (require_user, whitelist device)
Phase 2 – iOS Relay App (MVP)
SwiftUI app with permission screen
HealthKit background delivery for heart/steps/sleep
CoreMotion → motion_state
Location → geofence
Network.post → Gesahni ingest
Status screen: Sharing On, Last Sync, Count Today
Phase 3 – Alerts + Summary
Alert rules engine in FastAPI background task
/v1/health/summary endpoint
Today Card in Next.js + TV
Phase 4 – Watch Companion (Optional)
Watch battery % → ingest
Live Check-In (10-min HR stream via workout session)
Phase 5 – Enhancements
Wellbeing Radar (green/yellow/red badge)
Medication reminders via HealthKit/Reminders
Story capture nudges (sync with your memory vault)
HomeKit / TV automations (context-aware nudges)
Distribution
Free Developer Account: Sideload to phone, expires every 7 days. Good for proof-of-concept.
Apple Developer Program ($99/yr): Required for TestFlight or App Store distribution. Necessary for reliable long-term use.
Guardrails
Transparent consent screen with toggles (Health, Motion, Location, Watch).
"Stop Sharing" switch that revokes permissions + deletes anchors.
Privacy-first logs: only store what's needed (value_num, value_text).
TLS-secured comms to Gesahni.
Row-level auth per user.
Why This Wins
Compared to Apple's built-in Health Sharing:
✅ You control automation, alerts, escalation.
✅ Integrates with Gesahni memory & Home Assistant.
✅ Surfaces as Today Card + TV/phone banners.
✅ Allows future AI summaries ("summarize Mom's health last week").
✅ No subscriptions / vendor lock-in.
TL;DR Build Sequence
Backend ingest + table + metrics.
iOS Relay app → post real samples.
Today Card + 3 alerts.
Watch app (battery + Live Check-In).
Add Wellbeing Radar + fun automations.
This gives Mom a constant, safe, non-creepy digital safety net and folds her data into Gesahni's long-term memory.
