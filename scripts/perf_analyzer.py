#!/usr/bin/env python3
"""
Performance Baseline Analyzer

This script analyzes performance test results and compares them against baselines.
Used for CI/CD performance regression detection.
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np


class PerfAnalyzer:
    """Performance analyzer for baseline comparison and regression detection."""

    def __init__(self, baseline_dir: str = "perf_baselines"):
        self.baseline_dir = Path(baseline_dir)
        self.baseline_dir.mkdir(exist_ok=True)

    def parse_hey_csv(self, csv_file: Path) -> Dict[str, float]:
        """Parse hey CSV output and extract key metrics."""
        metrics = {}

        try:
            with open(csv_file, 'r') as f:
                # Skip header (hey doesn't produce headers)
                lines = f.readlines()
                if len(lines) < 1:
                    raise ValueError("CSV file too short")

                # First (and only) line contains summary
                summary_line = lines[0].strip()
                fields = summary_line.split(',')

                if len(fields) < 7:
                    raise ValueError("Invalid CSV format")

                # hey CSV format: response-time,response-time,response-time,response-time,response-time,response-time,status-code
                # But actually hey produces: total,avg,min,max,p50,p95,p99,status-codes
                metrics['total_requests'] = float(fields[0])
                metrics['avg_response_time'] = float(fields[1])
                metrics['min_response_time'] = float(fields[2])
                metrics['max_response_time'] = float(fields[3])
                metrics['p50_response_time'] = float(fields[4])
                metrics['p95_response_time'] = float(fields[5])
                metrics['p99_response_time'] = float(fields[6])

        except Exception as e:
            print(f"Error parsing CSV {csv_file}: {e}")
            return {}

        return metrics

    def save_baseline(self, endpoint: str, metrics: Dict[str, float], timestamp: Optional[str] = None) -> None:
        """Save performance metrics as baseline for future comparison."""
        if timestamp is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        baseline_file = self.baseline_dir / f"{endpoint.replace('/', '_').lstrip('_')}_baseline.json"

        baseline_data = {
            "endpoint": endpoint,
            "timestamp": timestamp,
            "metrics": metrics
        }

        with open(baseline_file, 'w') as f:
            json.dump(baseline_data, f, indent=2)

        print(f"✅ Baseline saved for {endpoint} to {baseline_file}")

    def load_baseline(self, endpoint: str) -> Optional[Dict]:
        """Load baseline metrics for an endpoint."""
        baseline_file = self.baseline_dir / f"{endpoint.replace('/', '_').lstrip('_')}_baseline.json"

        if not baseline_file.exists():
            return None

        try:
            with open(baseline_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading baseline for {endpoint}: {e}")
            return None

    def compare_with_baseline(self, endpoint: str, current_metrics: Dict[str, float], threshold_percent: float = 20.0) -> Tuple[bool, Dict]:
        """Compare current metrics with baseline and detect regressions."""
        baseline_data = self.load_baseline(endpoint)

        if not baseline_data:
            print(f"⚠️  No baseline found for {endpoint}")
            return False, {"error": "no_baseline"}

        baseline_metrics = baseline_data['metrics']
        comparison = {}

        # Compare key metrics
        key_metrics = ['p95_response_time', 'avg_response_time', 'p99_response_time']

        regression_detected = False

        for metric in key_metrics:
            if metric in current_metrics and metric in baseline_metrics:
                current_value = current_metrics[metric]
                baseline_value = baseline_metrics[metric]

                # Calculate percentage change
                if baseline_value > 0:
                    percent_change = ((current_value - baseline_value) / baseline_value) * 100
                else:
                    percent_change = 0

                comparison[metric] = {
                    "current": current_value,
                    "baseline": baseline_value,
                    "percent_change": percent_change,
                    "regression": percent_change > threshold_percent
                }

                if comparison[metric]["regression"]:
                    regression_detected = True

        return regression_detected, comparison

    def analyze_results_directory(self, results_dir: str, save_baselines: bool = False, threshold_percent: float = 20.0) -> int:
        """Analyze all results in a directory and compare with baselines."""
        results_path = Path(results_dir)

        if not results_path.exists():
            print(f"❌ Results directory not found: {results_dir}")
            return 1

        # Find all CSV files
        csv_files = list(results_path.glob("*.csv"))

        if not csv_files:
            print(f"❌ No CSV files found in {results_dir}")
            return 1

        print(f"📊 Analyzing {len(csv_files)} result files...")

        overall_regressions = 0

        for csv_file in csv_files:
            # Extract endpoint from filename
            filename = csv_file.stem
            # Remove timestamp suffix (assuming format: v1_endpoint_timestamp)
            parts = filename.split('_')
            # Find the timestamp pattern (14 digits) and remove everything after it
            endpoint_parts = []
            for i, part in enumerate(parts):
                if len(part) == 8 and part.isdigit():  # Date part like 20250910
                    break
                elif len(part) == 6 and part.isdigit():  # Time part like 122622
                    break
                endpoint_parts.append(part)

            # Convert back to endpoint path
            endpoint = "/" + "/".join(endpoint_parts)

            print(f"\n🔍 Analyzing {endpoint} ({csv_file.name})")

            # Parse metrics
            metrics = self.parse_hey_csv(csv_file)

            if not metrics:
                print("❌ Failed to parse metrics")
                continue

            # Save as baseline if requested
            if save_baselines:
                self.save_baseline(endpoint, metrics)

            # Compare with baseline
            regression, comparison = self.compare_with_baseline(endpoint, metrics, threshold_percent)

            # Check if comparison contains an error
            if isinstance(comparison, dict) and "error" in comparison:
                print(f"⚠️  Skipping {endpoint}: {comparison['error']}")
                continue

            if regression:
                print("❌ PERFORMANCE REGRESSION DETECTED!")
                overall_regressions += 1

                for metric, data in comparison.items():
                    if isinstance(data, dict) and data.get("regression", False):
                        print(f"   {metric}: {data['percent_change']:.1f}% increase "
                              f"({data['baseline']:.2f}ms → {data['current']:.2f}ms)")
            else:
                print("✅ No regression detected")

                # Show comparison data
                for metric, data in comparison.items():
                    if isinstance(data, dict):
                        percent_change = data.get("percent_change", 0)
                        print(f"   {metric}: {percent_change:+.1f}% "
                              f"({data['baseline']:.2f}ms → {data['current']:.2f}ms)")

        print("\n🎯 Analysis Complete")
        print(f"Total regressions: {overall_regressions}")

        if overall_regressions > 0:
            print("❌ CI FAILURE: Performance regressions detected!")
            return 1
        else:
            print("✅ CI SUCCESS: No performance regressions!")
            return 0


def main():
    parser = argparse.ArgumentParser(description="Performance Baseline Analyzer")
    parser.add_argument("--results-dir", required=True, help="Directory containing CSV results")
    parser.add_argument("--baseline-dir", default="perf_baselines", help="Directory for baseline files")
    parser.add_argument("--save-baselines", action="store_true", help="Save current results as new baselines")
    parser.add_argument("--threshold", type=float, default=20.0, help="Regression threshold percentage")
    parser.add_argument("--endpoint", help="Specific endpoint to analyze (optional)")

    args = parser.parse_args()

    analyzer = PerfAnalyzer(args.baseline_dir)

    if args.endpoint:
        # Analyze specific endpoint
        csv_file = Path(args.results_dir) / f"{args.endpoint.replace('/', '_').lstrip('_')}_*.csv"
        matching_files = list(Path(args.results_dir).glob(f"{args.endpoint.replace('/', '_').lstrip('_')}_*.csv"))

        if not matching_files:
            print(f"❌ No CSV file found for endpoint {args.endpoint}")
            return 1

        csv_file = matching_files[0]  # Take the first (most recent)
        metrics = analyzer.parse_hey_csv(csv_file)

        if not metrics:
            print("❌ Failed to parse metrics")
            return 1

        if args.save_baselines:
            analyzer.save_baseline(args.endpoint, metrics)

        regression, comparison = analyzer.compare_with_baseline(args.endpoint, metrics, args.threshold)

        if regression:
            print("❌ PERFORMANCE REGRESSION DETECTED!")
            return 1
        else:
            print("✅ No regression detected")
            return 0
    else:
        # Analyze all files in directory
        return analyzer.analyze_results_directory(args.results_dir, args.save_baselines, args.threshold)


if __name__ == "__main__":
    sys.exit(main())
