# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security
- **Authentication Redirects**: Fixed inconsistent OAuth redirect behavior by implementing secure cookie-based post-login navigation. Stop passing `?next=` to `/login` links; use cookie capture instead. Added comprehensive redirect sanitization to prevent open redirects, redirect loops, and path traversal attacks. ([docs/auth_redirects.md](docs/auth_redirects.md))
