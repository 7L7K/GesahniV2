#!/usr/bin/env python3
"""
Generate mock performance test results for demonstration and testing.

This script creates sample CSV files that simulate hey load testing output,
allowing the performance analyzer to be tested without requiring a running server.
"""

import csv
import random
from datetime import datetime
from pathlib import Path


def generate_mock_hey_csv(
    output_file: Path, endpoint: str, base_response_time: float = 50.0
):
    """Generate a mock CSV file that simulates hey output."""

    # Simulate realistic response time distribution
    def generate_response_times(count: int, base_time: float):
        times = []
        for _ in range(count):
            # Add some variance around the base time
            variance = random.uniform(-0.3, 0.7)  # Slightly skewed toward faster times
            time_ms = max(10, base_time * (1 + variance))
            times.append(time_ms)
        return sorted(times)

    # Generate 1000 sample response times
    response_times = generate_response_times(1000, base_response_time)

    # Calculate statistics
    avg_time = sum(response_times) / len(response_times)
    min_time = min(response_times)
    max_time = max(response_times)
    p50_time = response_times[int(len(response_times) * 0.5)]
    p95_time = response_times[int(len(response_times) * 0.95)]
    p99_time = response_times[int(len(response_times) * 0.99)]

    # Create CSV content (hey format)
    with open(output_file, "w", newline="") as f:
        writer = csv.writer(f)
        # hey CSV format: total,avg,min,max,p50,p95,p99
        writer.writerow(
            [
                len(response_times),  # total requests
                avg_time,  # avg
                min_time,  # min
                max_time,  # max
                p50_time,  # p50
                p95_time,  # p95
                p99_time,  # p99
            ]
        )

    print(f"✅ Generated mock results for {endpoint}:")
    print(f"   P95: {p95_time:.1f}ms, Avg: {avg_time:.1f}ms, Max: {max_time:.1f}ms")


def create_mock_baselines():
    """Create initial baseline files for testing."""

    baselines_dir = Path("perf_baselines")
    baselines_dir.mkdir(exist_ok=True)

    endpoints = [
        ("/v1/healthz/live", 25.0),  # Fast health check
        ("/v1/whoami", 75.0),  # Auth check with some processing
        ("/v1/auth/login", 150.0),  # Login with validation
        ("/v1/music/command", 100.0),  # Music command processing
    ]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for endpoint, base_time in endpoints:
        baseline_file = (
            baselines_dir / f"{endpoint.replace('/', '_').lstrip('_')}_baseline.json"
        )

        # Generate slightly better baseline performance (simulating optimization)
        baseline_p95 = base_time * 0.8  # 20% better than current

        baseline_data = {
            "endpoint": endpoint,
            "timestamp": timestamp,
            "metrics": {
                "total_requests": 1000.0,
                "avg_response_time": baseline_p95 * 0.7,
                "min_response_time": 5.0,
                "max_response_time": baseline_p95 * 3.0,
                "p50_response_time": baseline_p95 * 0.5,
                "p95_response_time": baseline_p95,
                "p99_response_time": baseline_p95 * 1.5,
            },
        }

        with open(baseline_file, "w") as f:
            import json

            json.dump(baseline_data, f, indent=2)

        print(f"✅ Created baseline for {endpoint}: P95 = {baseline_p95:.1f}ms")


def main():
    """Generate mock performance test results and demonstrate the analyzer."""

    print("🎭 Generating mock performance test results...")
    print("=" * 50)

    # Create output directory
    results_dir = Path("perf_results")
    results_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Generate mock results for each endpoint
    endpoints = [
        (
            "/v1/healthz/live",
            30.0,
        ),  # Current performance (slightly worse than baseline)
        ("/v1/whoami", 90.0),  # Current performance
        ("/v1/auth/login", 180.0),  # Current performance (regression!)
        ("/v1/music/command", 120.0),  # Current performance
    ]

    for endpoint, base_time in endpoints:
        filename = f"{endpoint.replace('/', '_').lstrip('_')}_{timestamp}.csv"
        output_file = results_dir / filename
        generate_mock_hey_csv(output_file, endpoint, base_time)

    print("\n📊 Creating baseline files for comparison...")
    create_mock_baselines()

    print("\n🔍 Running performance analysis...")
    print("-" * 30)

    # Run the analyzer
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "scripts/perf_analyzer.py",
            "--results-dir",
            str(results_dir),
            "--threshold",
            "20.0",
        ],
        capture_output=True,
        text=True,
    )

    print("Analyzer output:")
    print(result.stdout)
    if result.stderr:
        print("Errors:", result.stderr)

    print(f"\nExit code: {result.returncode}")
    print("\n🎯 Mock performance testing complete!")
    print(f"📁 Results in: {results_dir}")
    print(f"📁 Baselines in: perf_baselines")


if __name__ == "__main__":
    main()
