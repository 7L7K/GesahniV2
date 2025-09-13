# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security
- **Authentication Redirects**: Fixed inconsistent OAuth redirect behavior by implementing secure cookie-based post-login navigation. Stop passing `?next=` to `/login` links; use cookie capture instead. Added comprehensive redirect sanitization to prevent open redirects, redirect loops, and path traversal attacks. ([docs/auth_redirects.md](docs/auth_redirects.md))

### API Changes
- **Legacy Route Deprecation**: Implemented comprehensive deprecation framework for legacy API routes with RFC 8594 compliance. Added `LegacyHeadersMiddleware` that attaches deprecation headers (`Deprecation: true`, `Sunset`, `Link`) to `/v1/legacy/*` routes. Marked legacy music routes (`/state`, `/v1/legacy/state`) as deprecated with planned removal by 2026-03-13. Added `legacy_hits_total` Prometheus metric for usage tracking and kill criteria monitoring. ([DEPRECATIONS.md](DEPRECATIONS.md))

### Developer Experience
- **Route Census CLI**: Added `gesahni-routes` (alias: `gsr`) command to `gesahni-zshrc-config.sh` for quick route inventory with legacy route highlighting and count validation. Maintains known route count invariants for testing.
