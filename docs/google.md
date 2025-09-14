Google OAuth Flows

Enable Gmail first → enable Calendar later (incremental)

1) User toggles Gmail → OAuth to Google with Gmail scopes
2) Callback decodes `sub`, persists token row (user_id, provider=google, provider_iss, provider_sub)
3) Later user toggles Calendar → OAuth with Calendar scopes
4) Callback decodes `sub` and verifies it matches existing row → if match, DAO unions scopes and links lineage; UI flips after refetch

Mismatch account path

1) Existing Gmail connection for sub=A
2) User toggles Calendar and authenticates as sub=B
3) Callback detects mismatch (A != B) → returns `account_mismatch` error; tokens unchanged; UI shows hint to reconnect with the same account

Token rotation path

1) Refresh flow returns a new refresh_token
2) DAO inserts a new row, invalidates previous row, and sets `replaced_by_id`
3) `scope_union_since` preserved; `service_state` remains unchanged
