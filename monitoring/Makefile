.PHONY: validate help clean test-all

# Default target
validate: validate-config validate-rules validate-metrics

# Validate Prometheus configuration syntax
validate-config:
	@echo "🔍 Validating Prometheus configuration..."
	@promtool check config prometheus/prometheus.yml || (echo "❌ Prometheus config validation failed" && exit 1)
	@echo "✅ Prometheus configuration is valid"

# Validate recording and alert rules
validate-rules:
	@echo "🔍 Validating Prometheus rules..."
	@promtool check rules prometheus/recording_rules.yml || (echo "❌ Recording rules validation failed" && exit 1)
	@promtool check rules prometheus/alert_rules.yml || (echo "❌ Alert rules validation failed" && exit 1)
	@echo "✅ All Prometheus rules are valid"

# Validate that /metrics endpoint is responding
validate-metrics:
	@echo "🔍 Checking /metrics endpoint..."
	@curl -sf http://localhost:8000/metrics > /dev/null || (echo "❌ /metrics endpoint is not responding. Make sure Gesahni app is running on port 8000." && exit 1)
	@echo "✅ /metrics endpoint is responding"

# Test Alertmanager configuration
validate-alertmanager:
	@echo "🔍 Validating Alertmanager configuration..."
	@docker run --rm -v $(PWD)/alertmanager:/etc/alertmanager prom/alertmanager:latest --config.file=/etc/alertmanager/alertmanager.yml --dry-run || (echo "❌ Alertmanager config validation failed" && exit 1)
	@echo "✅ Alertmanager configuration is valid"

# Run all validations including Alertmanager
validate-all: validate validate-alertmanager

# Show help
help:
	@echo "Available targets:"
	@echo "  validate        - Run all validations (config, rules, metrics)"
	@echo "  validate-config - Validate Prometheus configuration syntax"
	@echo "  validate-rules  - Validate recording and alert rules syntax"
	@echo "  validate-metrics- Validate /metrics endpoint availability"
	@echo "  validate-alertmanager - Validate Alertmanager configuration"
	@echo "  validate-all    - Run all validations including Alertmanager"
	@echo "  help            - Show this help message"
	@echo ""
	@echo "Usage in CI:"
	@echo "  make -C monitoring validate"

# Clean up any temporary files
clean:
	@echo "🧹 Cleaning up temporary files..."
	@rm -f *.tmp *.log
	@echo "✅ Cleanup complete"
