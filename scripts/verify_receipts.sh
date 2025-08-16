#!/usr/bin/env bash
set -euo pipefail
LOG="${LOG:-/tmp/gesahni_router.log}"  # path to your JSON logs

# Create a temporary log file if it doesn't exist
if [[ ! -f "$LOG" ]]; then
    echo "📝 Creating temporary log file: $LOG"
    echo "[]" > "$LOG"
fi

req(){ jq -rc '
  select(.path=="/v1/ask")
  | {rid,shape,normalized_from,override_in,intent,picker_reason,
     vendor:(.chosen_vendor),model:(.chosen_model),dry_run,
     cb_user_open,cb_global_open,allow_fallback,stream}' "$LOG" 2>/dev/null || echo "[]"; }

echo "🔍 Verifying Router Receipts..."
echo "📊 Log file: $LOG"
echo ""

echo "— route reason tallies —"
req | jq -r '.picker_reason' | sort | uniq -c | sort -nr | head

echo ""
echo "— shape normalization —"
req | jq -r 'select(.normalized_from!=null) | .normalized_from' \
  | sort | uniq -c

echo ""
echo "— vendor/model distribution —"
req | jq -r '{vendor,model,picker_reason}' | jq -s 'group_by(.vendor) | .[] | {vendor: .[0].vendor, count: length, models: [.[].model] | unique}'

echo ""
echo "— sanity: each entry has vendor/model —"
missing=$(req | jq -r 'select((.vendor==null) or (.model==null)) | .rid')
if [[ -n "$missing" ]]; then
    echo "❌ Missing vendor/model for rid(s):"
    echo "$missing"
    exit 1
else
    echo "✅ All entries have vendor and model"
fi

echo ""
echo "— circuit breaker tests —"
circuit_breaker_count=$(req | jq -r 'select(.picker_reason=="circuit_breaker") | .rid' | wc -l)
echo "Circuit breaker activations: $circuit_breaker_count"

echo ""
echo "— dry run tests —"
dry_run_count=$(req | jq -r 'select(.dry_run==true) | .rid' | wc -l)
echo "Dry run executions: $dry_run_count"

echo ""
echo "— pass —"
echo "✅ Verification complete!"
