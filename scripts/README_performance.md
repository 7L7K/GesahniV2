# Performance Testing Setup

This directory contains performance testing tools for the GesahniV2 API.

## Overview

The performance testing setup includes:

1. **Load Testing**: Using `hey` to generate load on key endpoints
2. **Baseline Storage**: Storing performance metrics for regression detection
3. **CI Integration**: Automated performance checks in GitHub Actions
4. **Regression Detection**: Automatic failure when P95 response time regresses >20%

## Key Endpoints Tested

- `/v1/healthz/live` - Liveness health check
- `/v1/whoami` - Authentication status endpoint
- `/v1/auth/login` - Authentication endpoint
- `/v1/music/command` - Music control endpoint

## Files

- `perf_baseline.sh` - Main performance testing script
- `perf_analyzer.py` - Python script for analyzing results and detecting regressions
- `.github/workflows/performance.yml` - CI workflow for automated performance testing

## Usage

### Running Performance Tests Locally

1. Start the backend server:
   ```bash
   cd /path/to/gesahni
   ./scripts/backend-only.sh
   ```

2. Run performance baseline tests:
   ```bash
   ./scripts/perf_baseline.sh
   ```

3. Analyze results:
   ```bash
   python scripts/perf_analyzer.py --results-dir perf_results
   ```

### Saving New Baselines

To save current performance as new baselines:

```bash
python scripts/perf_analyzer.py --results-dir perf_results --save-baselines
```

### CI Integration

The performance tests run automatically on:
- Push to main/master branch
- Pull requests to main/master branch
- Manual workflow dispatch

**Note**: Performance tests are skipped on forks to avoid running on every PR.

## Configuration

### Environment Variables

- `BASE_URL` - API base URL (default: http://127.0.0.1:8000)
- `CONCURRENCY` - Number of concurrent connections (default: 10)
- `DURATION` - Test duration (default: 30s)
- `OUTPUT_DIR` - Results output directory (default: perf_results)

### Regression Threshold

The default regression threshold is 20% for P95 response time. This can be adjusted:

```bash
python scripts/perf_analyzer.py --results-dir perf_results --threshold 15.0
```

## Baseline Storage

Baselines are stored as JSON files in the `perf_baselines/` directory:

```
perf_baselines/
├── v1_healthz_live_baseline.json
├── v1_whoami_baseline.json
├── v1_auth_login_baseline.json
└── v1_music_command_baseline.json
```

Each baseline file contains:
- Endpoint path
- Timestamp of baseline creation
- Performance metrics (avg, p50, p95, p99 response times)

## CI Workflow

The GitHub Actions workflow:

1. Sets up the environment (Python, hey, Qdrant)
2. Starts the backend server
3. Runs performance tests
4. Analyzes results against baselines
5. Fails CI if regressions detected (>20% P95 increase)
6. Saves new baselines on main branch pushes

## Troubleshooting

### Server Won't Start

Ensure all required environment variables are set:

```bash
export JWT_SECRET="your_32_char_minimum_secret"
export DEV_MODE=1
export VECTOR_STORE=qdrant
export QDRANT_URL="http://localhost:6333"
```

### Qdrant Connection Issues

Make sure Qdrant is running:

```bash
docker run -d -p 6333:6333 qdrant/qdrant:latest
```

### Performance Test Failures

- Check that all endpoints are accessible
- Verify server is not rate-limiting requests
- Ensure sufficient system resources for concurrent requests

## Results Format

Performance results are stored as CSV files with the format:
`total_requests,avg_response_time,min_response_time,max_response_time,p50_response_time,p95_response_time,p99_response_time`

Example analysis output:
```
Endpoint: /v1/healthz/live
Results file: perf_results/v1_healthz_live_20240910_143000.csv
  Response time avg: 45.2ms
  Response time min: 12.1ms
  Response time max: 234.5ms
  Response time p50: 42.3ms
  Response time p95: 89.7ms
  Response time p99: 156.2ms
```

## Regression Detection

The analyzer compares current performance against stored baselines:

- **P95 Response Time**: Primary regression metric (20% threshold)
- **Average Response Time**: Secondary metric
- **P99 Response Time**: Worst-case performance metric

CI will fail if any endpoint shows regression beyond the threshold.
