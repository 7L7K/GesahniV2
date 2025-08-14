### TV / Granny Mode State Machine

- **Scenes**: `ambient`, `interactive`, `alert` managed in `frontend/src/state/sceneManager.ts` with guarded transitions. `alert` holds control until dismissed.
- **Transitions**: `toAmbient`, `toInteractive`, `toAlert` record cause and timestamp; interactive auto-returns to ambient after 8s.
- **Quiet hours**: Frontend flag `isQuietHours` and badge; toggled by selecting the “Quiet Hours” vibe.
- **Scheduler**: `SchedulerService` scores widgets, assigns primary/side/ticker every 3s, and nudges scene to interactive unless quiet hours.
- **External triggers**: WebSocket alerts trigger `ws_alert`; speech events mark `stt_partial`/`stt_final` and nudge scene.
- **APIs consumed**: TV calls server for photos, weather, alerts, preferences, and config; HA and status endpoints also exposed.

### Receipts

1) Scene types and causes
```5:15:frontend/src/state/sceneManager.ts
export type Scene = "ambient" | "interactive" | "alert";
export type SceneTransitionCause = ... | "ws_alert" | "stt_partial" | "stt_final" | ... | "quiet_hours";
```

2) Guarded transition behavior
```46:70:frontend/src/state/sceneManager.ts
if (current === "alert") return; // alert holds control
... set({ scene: "interactive", ... });
... set({ scene: "alert", ... });
```

3) Auto-return timer (8s)
```57:65:frontend/src/state/sceneManager.ts
const timer = setTimeout(() => { ... set({ scene: "ambient", lastCause: "timeout_auto_return" }) }, 8000);
```

4) Quiet hours flag and badge
```20:29:frontend/src/state/sceneManager.ts
isQuietHours: false; ... setQuietHours: (on) => set({ isQuietHours: on }),
```
```5:11:frontend/src/components/tv/QuietHoursBadge.tsx
const { isQuietHours } = useSceneManager(); ... {isQuietHours ? 'Quiet Hours' : 'Quiet filter off'}
```

5) Vibe switcher toggles quiet hours
```12:23:frontend/src/components/tv/layers/VibeSwitcher.tsx
const VIBES = ["Bright", "Calm", "High Contrast", "Quiet Hours"] as const;
... if (vibe === "Quiet Hours") setQuietHours(true); else setQuietHours(false);
```

6) Scheduler loop and scene nudge
```83:90:frontend/src/services/scheduler.ts
this.tick(); ... this.interval = setInterval(() => this.tick(), 3000);
```
```228:233:frontend/src/services/scheduler.ts
if (assign.primary && state.scene !== "alert" && !state.isQuietHours) {
  useSceneManager.getState().toInteractive("scheduler_primary_focus");
}
```

7) Speech-driven triggers
```21:26:frontend/src/components/tv/widgets/TranscriptSlate.tsx
(window as any).__lastTranscriptAt = Date.now();
if (!is_final) scene.toInteractive("stt_partial"); else scene.toInteractive("stt_final");
```

8) Alert triggers
```9:17:frontend/src/components/tv/layers/AlertLayer.tsx
const onIncoming = () => { setActive(true); scene.toAlert("ws_alert"); };
window.addEventListener("alert:incoming", onIncoming);
```

9) TV endpoints (photos/weather/alert/prefs/config)
```30:43:app/api/tv.py
@router.get("/tv/photos") ... return {"folder": base_url, "items": items}
```
```384:409:app/api/tv.py
@router.get("/tv/weather") ... return { city, now, today, tomorrow }
```
```412:421:app/api/tv.py
@router.post("/tv/alert") ... return {"status": "accepted", "kind": kind, "note": note}
```
```435:447:app/api/tv.py
@router.get("/tv/prefs") ... profile_store.get(user_id)
```
```568:637:app/api/tv.py
@router.put("/tv/config") ... validate quiet_hours HH:MM and broadcast ws event
```

10) TV page wires layers and scheduler
```16:36:frontend/src/app/tv/live/page.tsx
wsHub.start(); const detachUi = attachUiEffects(); ... <QuietHoursBadge /> <VibeSwitcher /> <AlertLayer />
```
