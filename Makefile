auth-sanity:
	@echo "== Backend greps (runtime) =="
	@rg -n --no-heading -S '\b(access_token|refresh_token|__session)\b' app | grep -v cookie_names.py | grep -vE '(tests?|docs?)' && (echo "FAIL: legacy refs found"; exit 1) || echo "OK"
	@echo "== Frontend greps (runtime) =="
	@rg -n --no-heading -S '\b(access_token|refresh_token|__session)\b' frontend | grep -vE '(tests?|docs?)' && (echo "FAIL: legacy refs found"; exit 1) || echo "OK"


