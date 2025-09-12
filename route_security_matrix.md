# FastAPI Route Security Matrix

## Summary
- **Total**: 171
- **Errors**: 15
- **Warnings (after allowlist)**: 15 (raw: 15)
- **public**: 160
- **token**: 8
- **token+csrf**: 0
- **admin**: 3

## PUBLIC Routes (160)

| Method | Path | Handler | CSRF | Admin | Exempt | InSchema | Evidence |
|--------|------|---------|------|-------|--------|----------|----------|
| GET | `/` | `app.api.root.root` |  |  |  |  |  |
| GET | `/__diag/events` | `app.main.create_app.<locals>.__diag_events` |  |  |  |  |  |
| GET | `/__diag/fingerprint` | `app.main.create_app.<locals>.__diag_fingerprint` |  |  |  |  |  |
| GET | `/__diag/startup` | `app.main.create_app.<locals>.__diag_startup` |  |  |  |  |  |
| GET | `/__diag/verify` | `app.main.create_app.<locals>.__diag_verify` |  |  |  |  |  |
| GET | `/admin/{path:path}` | `app.router.compat_api.admin_legacy_redirect` |  |  | compat_redirect |  |  |
| GET | `/api` | `app.api.root.api_info` |  |  |  |  |  |
| POST | `/ask` | `app.router.compat_api.ask_compat` |  |  | compat_redirect |  |  |
| OPTIONS | `/auth/apple/callback` | `app.api.util.apple_auth_callback_options` |  |  |  |  |  |
| OPTIONS | `/auth/apple/start` | `app.api.util.apple_auth_start_options` |  |  |  |  |  |
| OPTIONS | `/auth/token` | `app.api.util.auth_token_options` |  |  |  |  |  |
| GET | `/csrf` | `app.api.util.get_csrf` |  |  |  |  |  |
| OPTIONS | `/csrf` | `app.api.util.csrf_options` |  |  |  |  |  |
| POST | `/dev/mint_access` | `app.api.dev.mint_access` |  |  |  |  |  |
| GET | `/google/oauth/callback` | `app.router.compat_api.legacy_google_oauth_callback_compat` |  |  | compat_redirect |  |  |
| POST | `/google/oauth/callback` | `app.router.compat_api.legacy_google_oauth_callback_compat` |  |  | compat_redirect |  |  |
| GET | `/google/status` | `app.router.compat_api.google_status_compat` |  |  | compat_redirect |  |  |
| GET | `/health` | `app.router.compat_api.health_compat` |  |  | compat_redirect |  |  |
| OPTIONS | `/health` | `app.api.util.health_options` |  |  |  |  |  |
| GET | `/health/vector_store` | `app.api.health.health_vector_store` |  |  |  |  |  |
| GET | `/healthz` | `app.router.compat_api.healthz_compat` |  |  | compat_redirect |  |  |
| GET | `/healthz/deps` | `app.api.health.health_deps` |  |  |  |  |  |
| GET | `/healthz/live` | `app.api.health.health_live` |  |  |  | ✓ |  |
| GET | `/healthz/ready` | `app.api.health.health_ready` |  |  |  | ✓ |  |
| GET | `/metrics` | `app.api.metrics_root._metrics_route` |  |  |  |  |  |
| OPTIONS | `/metrics` | `app.api.util.metrics_options` |  |  |  |  |  |
| GET | `/ping` | `app.api.util.ping` |  |  |  |  |  |
| GET | `/spotify/status` | `app.router.compat_api.spotify_status_compat` |  |  | compat_redirect |  |  |
| GET | `/status` | `app.router.compat_api.status_compat` |  |  | compat_redirect |  |  |
| GET | `/test-errors/test/connection-error` | `app.test_error_normalization.test_connection_error` |  |  |  | ✓ |  |
| GET | `/test-errors/test/file-too-large` | `app.test_error_normalization.test_file_too_large` |  |  |  | ✓ |  |
| GET | `/test-errors/test/forbidden` | `app.test_error_normalization.test_forbidden` |  |  |  | ✓ |  |
| GET | `/test-errors/test/internal-error` | `app.test_error_normalization.test_internal_error` |  |  |  | ✓ |  |
| GET | `/test-errors/test/internal-error-helper` | `app.test_error_normalization.test_internal_error_helper` |  |  |  | ✓ |  |
| GET | `/test-errors/test/key-error` | `app.test_error_normalization.test_key_error` |  |  |  | ✓ |  |
| GET | `/test-errors/test/method-not-allowed` | `app.test_error_normalization.test_method_not_allowed` |  |  |  | ✓ |  |
| GET | `/test-errors/test/not-found` | `app.test_error_normalization.test_not_found` |  |  |  | ✓ |  |
| GET | `/test-errors/test/payload-too-large` | `app.test_error_normalization.test_payload_too_large` |  |  |  | ✓ |  |
| GET | `/test-errors/test/permission-error` | `app.test_error_normalization.test_permission_error` |  |  |  | ✓ |  |
| GET | `/test-errors/test/timeout-error` | `app.test_error_normalization.test_timeout_error` |  |  |  | ✓ |  |
| GET | `/test-errors/test/translate-common-exception` | `app.test_error_normalization.test_translate_common_exception` |  |  |  | ✓ |  |
| GET | `/test-errors/test/type-error` | `app.test_error_normalization.test_type_error` |  |  |  | ✓ |  |
| GET | `/test-errors/test/unauthorized` | `app.test_error_normalization.test_unauthorized` |  |  |  | ✓ |  |
| GET | `/test-errors/test/validation-error` | `app.test_error_normalization.test_validation_error` |  |  |  | ✓ |  |
| GET | `/test-errors/test/validation-error-helper` | `app.test_error_normalization.test_validation_error_helper` |  |  |  | ✓ |  |
| GET | `/test-errors/test/value-error` | `app.test_error_normalization.test_value_error` |  |  |  | ✓ |  |
| GET | `/v1/_diag/auth` | `app.api.debug.diag_auth` |  |  |  |  |  |
| GET | `/v1/_schema/error-envelope.json` | `app.api.schema.error_envelope_schema` |  |  |  |  |  |
| POST | `/v1/admin/backup` | `app.router.admin_api.admin_backup` |  |  |  | ✓ |  |
| GET | `/v1/admin/config` | `app.router.admin_api.admin_config` |  |  |  | ✓ |  |
| GET | `/v1/admin/config-check` | `app.router.admin_api.admin_config_check` |  |  |  | ✓ |  |
| GET | `/v1/admin/errors` | `app.router.admin_api.admin_errors` |  |  |  | ✓ |  |
| GET | `/v1/admin/flags` | `app.router.admin_api.admin_flags_get` |  |  |  | ✓ |  |
| POST | `/v1/admin/flags` | `app.router.admin_api.admin_flags_post` |  |  |  | ✓ |  |
| POST | `/v1/admin/flags/test` | `app.router.admin_api.admin_flags_test` |  |  |  | ✓ |  |
| GET | `/v1/admin/metrics` | `app.router.admin_api.admin_metrics` |  |  |  | ✓ |  |
| GET | `/v1/admin/ping` | `app.router.admin_api.admin_ping` |  |  |  | ✓ |  |
| GET | `/v1/admin/rbac/info` | `app.router.admin_api.admin_rbac_info` |  |  |  | ✓ |  |
| GET | `/v1/admin/retrieval/last` | `app.router.admin_api.admin_retrieval_last` |  |  |  | ✓ |  |
| GET | `/v1/admin/router/decisions` | `app.router.admin_api.admin_router_decisions` |  |  |  | ✓ |  |
| GET | `/v1/admin/system/status` | `app.router.admin_api.admin_system_status` |  |  |  | ✓ |  |
| GET | `/v1/admin/tokens/google` | `app.router.admin_api.admin_google_tokens` |  |  |  | ✓ |  |
| GET | `/v1/admin/users/me` | `app.router.admin_api.admin_users_me` |  |  |  | ✓ |  |
| POST | `/v1/ask` | `app.router.ask_api.ask_endpoint` |  |  |  | ✓ |  |
| GET | `/v1/ask/replay/{rid}` | `app.router.ask_api.ask_replay` |  |  |  |  |  |
| GET | `/v1/auth/clerk/finish` | `app.api.auth.clerk_finish` |  |  |  | ✓ |  |
| POST | `/v1/auth/clerk/finish` | `app.api.auth.clerk_finish` |  |  |  | ✓ |  |
| GET | `/v1/auth/examples` | `app.api.auth.token_examples` |  |  |  | ✓ |  |
| GET | `/v1/auth/google/callback` | `app.router.compat_api.legacy_auth_google_callback_compat` |  |  | compat_redirect |  |  |
| POST | `/v1/auth/google/callback` | `app.router.compat_api.legacy_auth_google_callback_compat` |  |  | compat_redirect |  |  |
| POST | `/v1/auth/login` | `app.api.auth.login_v1` |  |  |  | ✓ |  |
| POST | `/v1/auth/register` | `app.api.auth.register_v1` |  |  |  | ✓ |  |
| POST | `/v1/auth/token` | `app.api.auth.dev_password_token` |  |  |  | ✓ |  |
| GET | `/v1/budget` | `app.status.budget_status_alias` |  |  |  | ✓ |  |
| GET | `/v1/calendar/list` | `app.api.calendar.list_all` |  |  |  | ✓ |  |
| GET | `/v1/calendar/next` | `app.api.calendar.next_three` |  |  |  | ✓ |  |
| GET | `/v1/calendar/today` | `app.api.calendar.list_today` |  |  |  | ✓ |  |
| GET | `/v1/care/alerts` | `app.api.care.list_alerts` |  |  |  | ✓ |  |
| POST | `/v1/care/alerts` | `app.api.care.create_alert` |  |  |  | ✓ |  |
| POST | `/v1/care/alerts/{alert_id}/ack` | `app.api.care.ack_alert` |  |  |  | ✓ |  |
| POST | `/v1/care/alerts/{alert_id}/resolve` | `app.api.care.resolve_alert` |  |  |  | ✓ |  |
| GET | `/v1/care/device_status` | `app.api.care.device_status` |  |  |  | ✓ |  |
| POST | `/v1/care/devices/{device_id}/heartbeat` | `app.api.care.heartbeat` |  |  |  | ✓ |  |
| GET | `/v1/care/sessions` | `app.api.care.list_care_sessions` |  |  |  | ✓ |  |
| GET | `/v1/config` | `app.status.config` |  |  |  | ✓ |  |
| GET | `/v1/debug/config` | `app.api.debug.debug_config` |  |  |  |  |  |
| GET | `/v1/debug/oauth` | `app.api.debug.debug_oauth_page` |  |  |  |  |  |
| GET | `/v1/debug/oauth/config` | `app.api.debug.debug_oauth_config` |  |  |  |  |  |
| GET | `/v1/debug/oauth/routes` | `app.api.debug.debug_oauth_routes` |  |  |  |  |  |
| GET | `/v1/debug/token-health` | `app.api.debug.token_health` |  |  |  |  |  |
| GET | `/v1/docs/ws` | `app.api.debug.ws_helper_page` |  |  |  |  |  |
| GET | `/v1/finish` | `app.api.auth.finish_clerk_login` |  |  |  |  |  |
| POST | `/v1/finish` | `app.api.auth.finish_clerk_login` |  |  |  |  |  |
| GET | `/v1/google/callback` | `app.api.google_oauth.google_callback` |  |  | oauth_callback |  |  |
| GET | `/v1/google/google/oauth/callback` | `app.api.google_oauth.google_callback_root` |  |  |  |  |  |
| GET | `/v1/google/login_url` | `app.api.google_oauth.google_login_url` |  |  |  | ✓ |  |
| GET | `/v1/ha/entities` | `app.api.ha.ha_entities` |  |  |  | ✓ |  |
| GET | `/v1/ha/health` | `app.api.ha.ha_health` |  |  |  | ✓ |  |
| GET | `/v1/ha/resolve` | `app.api.ha.ha_resolve` |  |  |  | ✓ |  |
| POST | `/v1/ha/service` | `app.api.ha.ha_service` |  |  |  | ✓ |  |
| POST | `/v1/ha/webhook` | `app.api.ha.ha_webhook` |  |  | webhook | ✓ |  |
| GET | `/v1/health` | `app.api.health.health_combined` |  |  |  | ✓ |  |
| GET | `/v1/health/chroma` | `app.api.health.health_chroma` |  |  |  |  |  |
| GET | `/v1/health/qdrant` | `app.api.health.health_qdrant` |  |  |  |  |  |
| GET | `/v1/health/vector_store` | `app.api.health.health_vector_store` |  |  |  |  |  |
| GET | `/v1/healthz` | `app.api.health.healthz_v1` |  |  |  | ✓ |  |
| GET | `/v1/integrations/spotify/callback` | `app.router.compat_api.legacy_spotify_integrations_callback_compat` |  |  | compat_redirect |  |  |
| POST | `/v1/integrations/spotify/callback` | `app.router.compat_api.legacy_spotify_integrations_callback_compat` |  |  | compat_redirect |  |  |
| GET | `/v1/integrations/spotify/connect` | `app.router.compat_api.legacy_spotify_integrations_connect_compat` |  |  | compat_redirect |  |  |
| POST | `/v1/integrations/spotify/connect` | `app.router.compat_api.legacy_spotify_integrations_connect_compat` |  |  | compat_redirect |  |  |
| DELETE | `/v1/integrations/spotify/disconnect` | `app.router.compat_api.legacy_spotify_integrations_disconnect_compat` |  |  | compat_redirect |  |  |
| GET | `/v1/integrations/spotify/disconnect` | `app.router.compat_api.legacy_spotify_integrations_disconnect_compat` |  |  | compat_redirect |  |  |
| GET | `/v1/integrations/spotify/status` | `app.router.compat_api.legacy_spotify_integrations_status_compat` |  |  | compat_redirect |  |  |
| GET | `/v1/login` | `app.router.compat_api.login_compat` |  |  | compat_redirect |  |  |
| POST | `/v1/login` | `app.router.compat_api.login_compat` |  |  | compat_redirect |  |  |
| GET | `/v1/logout` | `app.router.compat_api.logout_compat` |  |  | compat_redirect |  |  |
| POST | `/v1/logout` | `app.router.compat_api.logout_compat` |  |  | compat_redirect |  |  |
| GET | `/v1/me` | `app.api.me.me` |  |  |  | ✓ |  |
| GET | `/v1/mock/set_access_cookie` | `app.api.auth.mock_set_access_cookie` |  |  |  |  |  |
| POST | `/v1/music` | `app.api.music_http.music_command` |  |  |  | ✓ | csrf_validate |
| POST | `/v1/music/device` | `app.api.music_http.transfer_playback_device` |  |  |  | ✓ |  |
| GET | `/v1/music/devices` | `app.api.music_http.list_devices` |  |  |  | ✓ |  |
| GET | `/v1/pats` | `app.api.auth.list_pats` |  |  |  | ✓ |  |
| GET | `/v1/ping` | `app.api.health.ping_vendor_health` |  |  |  |  |  |
| GET | `/v1/queue` | `app.api.music_http.get_queue` |  |  |  | ✓ |  |
| GET | `/v1/recommendations` | `app.api.music_http.recommendations` |  |  |  | ✓ |  |
| GET | `/v1/refresh` | `app.router.compat_api.refresh_compat` |  |  | compat_redirect |  |  |
| POST | `/v1/refresh` | `app.router.compat_api.refresh_compat` |  |  | compat_redirect |  |  |
| GET | `/v1/register` | `app.router.compat_api.register_compat` |  |  | compat_redirect |  |  |
| POST | `/v1/register` | `app.router.compat_api.register_compat` |  |  | compat_redirect |  |  |
| POST | `/v1/restore_volume` | `app.api.music_http.restore_volume` |  |  |  | ✓ |  |
| GET | `/v1/sessions` | `app.api.me.sessions` |  |  |  | ✓ |  |
| GET | `/v1/sessions/paginated` | `app.api.me.sessions_paginated` |  |  |  | ✓ |  |
| POST | `/v1/sessions/{sid}/revoke` | `app.api.me.revoke_session` |  |  |  | ✓ |  |
| GET | `/v1/spotify/callback` | `app.api.spotify.spotify_callback` |  |  | webhook |  |  |
| GET | `/v1/spotify/callback-test` | `app.api.spotify.spotify_callback_test` |  |  |  |  |  |
| GET | `/v1/spotify/connect` | `app.api.spotify.spotify_connect` |  |  |  | ✓ |  |
| GET | `/v1/spotify/debug` | `app.api.spotify.spotify_debug` |  |  |  |  |  |
| GET | `/v1/spotify/debug-cookie` | `app.api.spotify.spotify_debug_cookie` |  |  |  |  |  |
| GET | `/v1/spotify/debug/store` | `app.api.spotify.debug_oauth_store` |  |  |  |  |  |
| DELETE | `/v1/spotify/disconnect` | `app.api.spotify.spotify_disconnect` |  |  |  | ✓ |  |
| GET | `/v1/spotify/health` | `app.api.spotify.spotify_health` |  |  |  | ✓ |  |
| GET | `/v1/spotify/status` | `app.api.spotify.spotify_status` |  |  |  | ✓ |  |
| POST | `/v1/spotify/test/full_flow` | `app.api.spotify.test_full_flow` |  |  |  |  |  |
| POST | `/v1/spotify/test/store_tx` | `app.api.spotify.test_store_tx` |  |  |  |  |  |
| GET | `/v1/state` | `app.api.music_http.music_state` |  |  |  | ✓ |  |
| GET | `/v1/status` | `app.status.full_status` |  |  |  | ✓ |  |
| GET | `/v1/status/budget` | `app.status.budget_status` |  |  |  | ✓ |  |
| GET | `/v1/status/features` | `app.status.features` |  |  |  | ✓ |  |
| GET | `/v1/status/ha` | `app.status.ha_status` |  |  |  | ✓ |  |
| GET | `/v1/status/llama` | `app.status.llama_status` |  |  |  | ✓ |  |
| GET | `/v1/status/preflight` | `app.api.preflight.preflight` |  |  |  | ✓ |  |
| GET | `/v1/status/rate_limit` | `app.status.rate_limit_status_public` |  |  |  | ✓ |  |
| POST | `/v1/tts/speak` | `app.api.tts.speak` |  |  |  | ✓ |  |
| GET | `/v1/tv/calendar/next` | `app.api.calendar.tv_calendar_next_alias` |  |  |  |  |  |
| GET | `/v1/vendor-health` | `app.api.health.get_vendor_health_status` |  |  |  |  |  |
| POST | `/v1/vibe` | `app.api.music_http.set_vibe` |  |  |  | ✓ |  |
| GET | `/v1/whoami` | `app.api.auth.whoami` |  |  |  |  |  |
| OPTIONS | `/v1/{path:path}` | `app.api.util.v1_options_handler` |  |  |  |  |  |
| GET | `/whoami` | `app.router.compat_api.whoami_compat` |  |  | compat_redirect |  |  |

## TOKEN Routes (8)

| Method | Path | Handler | CSRF | Admin | Exempt | InSchema | Evidence |
|--------|------|---------|------|-------|--------|----------|----------|
| POST | `/v1/auth/logout` | `app.api.auth.logout` |  |  | token_exchange | ✓ | require_auth_no_csrf |
| POST | `/v1/auth/logout_all` | `app.api.auth.logout_all` |  |  |  | ✓ | require_auth_no_csrf |
| POST | `/v1/auth/refresh` | `app.api.auth.refresh` |  |  | token_exchange | ✓ | require_auth_no_csrf |
| POST | `/v1/auth/refresh` | `app.api.auth_router_refresh.refresh` |  |  | token_exchange | ✓ | require_auth_no_csrf |
| POST | `/v1/care/sessions` | `app.api.care.create_care_session` |  |  |  | ✓ | require_auth_with_csrf |
| PATCH | `/v1/care/sessions/{session_id}` | `app.api.care.patch_care_session` |  |  |  | ✓ | require_auth_with_csrf |
| POST | `/v1/pats` | `app.api.auth.create_pat` |  |  |  | ✓ | require_auth_with_csrf |
| DELETE | `/v1/pats/{pat_id}` | `app.api.auth.revoke_pat` |  |  |  |  | require_auth_with_csrf |

## ADMIN Routes (3)

| Method | Path | Handler | CSRF | Admin | Exempt | InSchema | Evidence |
|--------|------|---------|------|-------|--------|----------|----------|
| GET | `/v1/status/integrations` | `app.status.integrations_status` |  | ✓ |  | ✓ | require_admin |
| GET | `/v1/status/observability` | `app.status.observability_metrics` |  | ✓ |  | ✓ | require_admin |
| GET | `/v1/status/vector_store` | `app.status.status_vector_store` |  | ✓ |  | ✓ | require_admin |
## POLICY ERRORS

- [ERROR] ADMIN_PATH_WEAK_PROTECTION: GET /v1/admin/ping — /v1/admin/* routes must require admin
- [ERROR] ADMIN_PATH_WEAK_PROTECTION: GET /v1/admin/rbac/info — /v1/admin/* routes must require admin
- [ERROR] ADMIN_PATH_WEAK_PROTECTION: GET /v1/admin/system/status — /v1/admin/* routes must require admin
- [ERROR] ADMIN_PATH_WEAK_PROTECTION: GET /v1/admin/tokens/google — /v1/admin/* routes must require admin
- [ERROR] ADMIN_PATH_WEAK_PROTECTION: GET /v1/admin/metrics — /v1/admin/* routes must require admin
- [ERROR] ADMIN_PATH_WEAK_PROTECTION: GET /v1/admin/router/decisions — /v1/admin/* routes must require admin
- [ERROR] ADMIN_PATH_WEAK_PROTECTION: GET /v1/admin/config — /v1/admin/* routes must require admin
- [ERROR] ADMIN_PATH_WEAK_PROTECTION: GET /v1/admin/errors — /v1/admin/* routes must require admin
- [ERROR] ADMIN_PATH_WEAK_PROTECTION: GET /v1/admin/flags — /v1/admin/* routes must require admin
- [ERROR] ADMIN_PATH_WEAK_PROTECTION: POST /v1/admin/flags — /v1/admin/* routes must require admin
- [ERROR] ADMIN_PATH_WEAK_PROTECTION: POST /v1/admin/flags/test — /v1/admin/* routes must require admin
- [ERROR] ADMIN_PATH_WEAK_PROTECTION: GET /v1/admin/users/me — /v1/admin/* routes must require admin
- [ERROR] ADMIN_PATH_WEAK_PROTECTION: GET /v1/admin/retrieval/last — /v1/admin/* routes must require admin
- [ERROR] ADMIN_PATH_WEAK_PROTECTION: GET /v1/admin/config-check — /v1/admin/* routes must require admin
- [ERROR] ADMIN_PATH_WEAK_PROTECTION: POST /v1/admin/backup — /v1/admin/* routes must require admin

## WARNINGS (after allowlist)

- [WARN] CANONICAL_NOT_IN_SCHEMA: GET /v1/ask/replay/{rid} — Canonical route missing from schema
- [WARN] CANONICAL_NOT_IN_SCHEMA: GET /v1/whoami — Canonical route missing from schema
- [WARN] CANONICAL_NOT_IN_SCHEMA: DELETE /v1/pats/{pat_id} — Canonical route missing from schema
- [WARN] CANONICAL_NOT_IN_SCHEMA: POST /v1/finish — Canonical route missing from schema
- [WARN] CANONICAL_NOT_IN_SCHEMA: GET /v1/finish — Canonical route missing from schema
- [WARN] CANONICAL_NOT_IN_SCHEMA: GET /v1/google/google/oauth/callback — Canonical route missing from schema
- [WARN] CANONICAL_NOT_IN_SCHEMA: GET /v1/tv/calendar/next — Canonical route missing from schema
- [WARN] CANONICAL_NOT_IN_SCHEMA: GET /v1/spotify/callback — Canonical route missing from schema
- [WARN] CANONICAL_NOT_IN_SCHEMA: GET /v1/ping — Canonical route missing from schema
- [WARN] CANONICAL_NOT_IN_SCHEMA: GET /v1/health/vector_store — Canonical route missing from schema
- [WARN] CANONICAL_NOT_IN_SCHEMA: GET /v1/health/qdrant — Canonical route missing from schema
- [WARN] CANONICAL_NOT_IN_SCHEMA: GET /v1/health/chroma — Canonical route missing from schema
- [WARN] CANONICAL_NOT_IN_SCHEMA: OPTIONS /v1/{path:path} — Canonical route missing from schema
- [WARN] CANONICAL_NOT_IN_SCHEMA: GET /v1/docs/ws — Canonical route missing from schema
- [WARN] CANONICAL_NOT_IN_SCHEMA: GET /v1/_diag/auth — Canonical route missing from schema