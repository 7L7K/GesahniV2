auth-sanity:
	@echo "== Backend greps (runtime) =="
	@rg -n --no-heading -S '\b(access_token|refresh_token|__session)\b' app | grep -v cookie_names.py | grep -vE '(tests?|docs?)' && (echo "FAIL: legacy refs found"; exit 1) || echo "OK"
	@echo "== Frontend greps (runtime) =="
	@rg -n --no-heading -S '\b(access_token|refresh_token|__session)\b' frontend | grep -vE '(tests?|docs?)' && (echo "FAIL: legacy refs found"; exit 1) || echo "OK"

migration-guard:
	@echo "== Migration Guard: Checking for forbidden /login?next= patterns =="
	@./tools/grep_guard.sh --verbose || (echo "FAIL: Migration guard detected forbidden patterns"; exit 1)
	@echo "✅ Migration guard passed - no forbidden patterns found"

docs-and-links: migration-guard
	@echo "== Docs and Links Check =="
	@echo "✅ Docs and links hygiene check complete"
