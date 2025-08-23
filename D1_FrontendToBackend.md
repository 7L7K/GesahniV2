Map Next.js routes (/, /login, /capture, /settings, /admin, /tv/*) to: rendered screens/states, backend endpoints called, cookies/headers expected, and WebSocket subscriptions. End with Where I got this.

## /
- Rendered screens/states
  - Chat with streaming responses; music widgets: NowPlaying, Discovery, Queue, MoodDial, DevicePicker.
  - Auth states: authed vs unauth banner; onboarding redirect when not completed.
- Backend endpoints called
  - GET /v1/whoami (auth probe; layout bootstrap)
  - POST /v1/ask with Accept: text/event-stream or application/json (chat streaming)
  - GET /v1/state (music state)
  - GET /v1/queue (music queue)
  - GET /v1/recommendations (music discovery)
  - GET /v1/music/devices (device list)
  - POST /v1/music (play/pause/next/previous/volume)
  - POST /v1/vibe (set vibe)
  - POST /v1/music/device (select playback device)
- Cookies/headers expected
  - Either Authorization: Bearer <access_token> (header-auth mode) or HttpOnly cookies access_token/refresh_token (cookie-auth mode). All requests sent with credentials: include.
  - On 401: POST /v1/refresh to rotate tokens from refresh_token cookie/body.
  - Mutations send X-CSRF when a csrf_token cookie exists (CSRFMiddleware server-side).
  - 429 handling listens for Retry-After and X-RateLimit-Remaining when present.
- WebSocket subscriptions
  - ws /v1/ws/music (topics: music.state, music.queue.updated). Token passed as access_token query param in header mode, else via cookie.

## /login
- Rendered screens/states
  - Username/password login or register; Google OAuth button; success redirects to next param.
- Backend endpoints called
  - POST /v1/login (issue access/refresh; also sets HttpOnly cookies)
  - POST /v1/register (create account)
  - GET /v1/google/auth/login_url?next=<path> (get Google OAuth URL)
  - POST /v1/refresh (optional, to rotate/set HttpOnly cookies after redirect with tokens)
- Cookies/headers expected
  - Login page stores tokens in localStorage in header mode and sets auth:hint=1 cookie. Next.js middleware on /login captures access_token/refresh_token query params and sets HttpOnly cookies then redirects to next.
- WebSocket subscriptions
  - None on this page.

## /capture
- Rendered screens/states
  - Recorder UI (camera/mic), live transcript, recording/paused/uploading states; auth guard client-side.
- Backend endpoints called
  - POST /v1/capture/start (begin session)
  - WS /v1/transcribe (live STT; emits stt.partial, stt.final, tts.start, tts.stop)
  - POST /v1/capture/save multipart/form-data (audio, video, transcript)
- Cookies/headers expected
  - Same auth model as /. Mutations include X-CSRF when cookie present.
  - Sets auth:hint cookie for SSR-friendly gating.
- WebSocket subscriptions
  - ws /v1/transcribe (token in query for header mode; otherwise cookie).

## /settings
- Rendered screens/states
  - Profile form, Voice & Budget panel, Sessions panel, Security PATs; redirects to /login on 401/403.
- Backend endpoints called
  - GET /v1/profile; POST /v1/profile
  - GET /v1/budget
  - GET /v1/sessions; POST /v1/sessions/{sid}/revoke
  - GET /v1/pats; POST /v1/pats
- Cookies/headers expected
  - Same auth model as /. Mutations include X-CSRF when cookie present.
- WebSocket subscriptions
  - None on this page.

## /admin
- Rendered screens/states
  - Router Decisions table with filters/pagination; Self-review and Errors panels. Admin TV Config editor under /admin/tv-config; Memory Ingest under /admin/ingest.
- Backend endpoints called
  - GET /v1/admin/router/decisions?token=<ADMIN_TOKEN>&…
  - GET /v1/admin/errors?token=<ADMIN_TOKEN>
  - GET /v1/admin/self_review?token=<ADMIN_TOKEN>
  - Admin TV Config editor: GET /v1/tv/config?resident_id=<id>&token=<ADMIN_TOKEN>; PUT /v1/tv/config?resident_id=<id>&token=<ADMIN_TOKEN>
  - Admin Ingest: POST /v1/memory/ingest multipart/form-data (file or url)
- Cookies/headers expected
  - Same auth model as /. Admin APIs additionally require token query param that must match ADMIN_TOKEN env (relaxed in tests). Mutations include X-CSRF when cookie present.
- WebSocket subscriptions
  - Admin TV Config editor optionally opens ws /v1/ws/care and subscribes to resident:{id} to observe tv.config.updated.

## /tv/*
- /tv (home)
  - Rendered: tile launcher; no immediate API.
  - WS: none.
- /tv/live (full-screen TV experience)
  - Rendered: Backdrop, PrimaryStage, SideRail, FooterRibbon, QuietHoursBadge, AlertLayer, VibeSwitcher; remote control keymap; UI effects duck/restore volume.
  - Backend: POST /v1/music (duck/restore/play/pause); POST /v1/music/restore; POST /v1/vibe.
  - WS: /v1/ws/music (music.state); /v1/ws/care (subscribe {action:"subscribe",topic:"resident:me"}; events: alert.*, device.heartbeat, tv.config.updated).
  - Cookies/headers: same as /. WS token via query in header mode or via cookie.
- /tv/music
  - Rendered: Preset play buttons, transport buttons.
  - Backend: POST /v1/tv/music/play?preset=<name>
  - WS: none.
- /tv/weather
  - Rendered: Current/today/tomorrow tiles; status line.
  - Backend: GET /v1/tv/weather
  - WS: none.
- /tv/calendar
  - Rendered: Today’s events list.
  - Backend: EXPECTED GET /v1/tv/calendar/next
  - WS: none.
  - UNKNOWN: Backend provides GET /v1/calendar/next (not /v1/tv/calendar/next). Frontend likely should call /v1/calendar/next.
- /tv/photos
  - Rendered: Slideshow with controls; favorite button.
  - Backend: GET /v1/tv/photos; POST /v1/tv/photos/favorite?name=<file>
  - WS: none.
- /tv/contacts
  - Rendered: Contacts grid; confirm modal; success message.
  - Backend: GET /v1/tv/contacts; POST /v1/tv/contacts/call?name=<contact>
  - WS: none.
- /tv/reminders
  - Rendered: Add reminder quick list (local-only display).
  - Backend: POST /v1/reminders (frontend currently sends ?text=… without JSON body)
  - WS: none.
  - UNKNOWN: Backend expects JSON body {text, when, channel?} (and requires when). Frontend sends only a query param. Align by sending JSON per API or relaxing server schema.
- /tv/listening
  - Rendered: TV capture/listening view with Yes/No bar and live caption.
  - Backend: POST /v1/capture/start; WS /v1/transcribe; POST /v1/capture/save
  - WS: /v1/transcribe (emits stt.* events)

Notes on auth/cookies/common headers
- Header vs cookie auth: controlled in frontend by NEXT_PUBLIC_HEADER_AUTH_MODE. In header mode, Authorization: Bearer <access_token> is sent and wsUrl appends ?access_token=…; in cookie mode, HttpOnly cookies are relied on and ws auth falls back to cookies via verify_ws.
- Auth hint: Client sets auth:hint=1 after login to gate SSR routes; middleware on /login captures tokens from query and sets cookies + auth:hint.
- CSRF: Client sends X-CSRF for mutating requests when a csrf_token cookie is present; server has CSRFMiddleware enabled.
- Rate limiting: Server adds Retry-After (and sometimes X-RateLimit-Remaining per problem+json flow). Client surfaces a rate-limit toast.

Where I got this
- Frontend
  - frontend/src/lib/api.ts (API helpers, auth/cookies, SSE, wsUrl)
  - frontend/src/app/layout.tsx (bootstrap whoami)
  - frontend/src/app/page.tsx (/, chat + music usage)
  - frontend/src/app/login/page.tsx; frontend/src/middleware.ts (/login, OAuth flow cookies)
  - frontend/src/app/capture/page.tsx; frontend/src/components/CaptureMode.tsx; frontend/src/components/recorder/useRecorder.ts (/capture flows, WS /v1/transcribe)
  - frontend/src/app/settings/page.tsx
  - frontend/src/app/admin/page.tsx; frontend/src/app/admin/ingest/page.tsx; frontend/src/app/admin/tv-config/page.tsx
  - frontend/src/services/wsHub.ts; frontend/src/lib/uiEffects.ts (TV live WS + controls)
  - TV routes: frontend/src/app/tv/*.tsx and widgets/surfaces under frontend/src/components/tv/** (weather, calendar, photos, contacts, live, listening, music)
- Backend
  - app/main.py (router includes; WS endpoints /v1/transcribe, versioned routers)
  - app/api/ask.py (/v1/ask streaming)
  - app/api/auth.py (/v1/whoami, sessions, pats)
  - app/auth.py (/v1/register, /v1/login, /v1/refresh, /v1/logout)
  - app/api/models.py (/v1/models)
  - app/status.py (/v1/budget)
  - app/api/profile.py (/v1/profile, /v1/onboarding/*)
  - app/api/music.py (/v1/state, /v1/queue, /v1/recommendations, /v1/music*, ws /v1/ws/music)
  - app/api/tv.py (/v1/tv/photos*, /v1/tv/weather, /v1/tv/music/play, /v1/tv/config*)
  - app/api/calendar.py (/v1/calendar/*)
  - app/api/contacts.py (TV contacts + call)
  - app/api/care_ws.py (ws /v1/ws/care, topics/events)
  - app/api/reminders.py (/v1/reminders)
  - app/integrations/google/routes.py (/v1/google/auth/login_url + callback)
  - app/security.py (verify_token, verify_ws, rate-limit semantics)
