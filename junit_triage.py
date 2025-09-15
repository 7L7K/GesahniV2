#!/usr/bin/env python3
"""
junit_triage.py — quick triage for large pytest suites.

Usage:
  python junit_triage.py path/to/junit.xml [--top 20]

Outputs:
  - Console summary (totals, heatmap by package, top error clusters)
  - CSV at ./triage_summary.csv (test, status, file, class, time, message, package)
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path


def norm_msg(msg: str) -> str:
    if not msg:
        return ""
    # Collapse numbers, UUIDs, timestamps to reduce noise in clustering
    msg = re.sub(r"\b[0-9a-fA-F]{8,}\b", "<HEX>", msg)
    msg = re.sub(
        r"\b\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?)?\b", "<DATE>", msg
    )
    msg = re.sub(r"\b\d+\b", "<N>", msg)
    # Keep first ~300 chars for signature
    return msg.strip().replace("\n", " ")[:300]


def package_of(file_path: str) -> str:
    if not file_path:
        return ""
    # Convert tests/foo/bar/test_baz.py -> tests.foo.bar
    p = Path(file_path)
    parts = list(p.parts)
    if parts and parts[-1].startswith("test_"):
        parts = parts[:-1]
    if parts and parts[-1].endswith(".py"):
        parts[-1] = parts[-1].removesuffix(".py")
    return ".".join([seg for seg in parts if seg not in ("", ".")])


def parse_junit(xml_path: Path):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    # Pytest may nest testsuite(s) within a root testsuite or testsuites
    cases = []
    for elem in root.iter():
        if elem.tag.endswith("testcase"):
            cases.append(elem)
    return cases


def status_of(tc) -> str:
    for child in tc:
        tag = child.tag.split("}")[-1]
        if tag in ("failure", "error"):
            return tag
        if tag == "skipped":
            return "skipped"
    return "passed"


def message_of(tc) -> str:
    for child in tc:
        tag = child.tag.split("}")[-1]
        if tag in ("failure", "error", "skipped"):
            msg = (child.get("message") or "") + " " + (child.text or "")
            return msg.strip()
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xml", type=Path)
    ap.add_argument("--top", type=int, default=20, help="How many top items to show")
    args = ap.parse_args()

    cases = parse_junit(args.xml)

    totals = Counter()
    by_package = Counter()
    by_cluster = Counter()
    cluster_examples = defaultdict(list)

    rows = []
    for tc in cases:
        classname = tc.get("classname") or ""
        name = tc.get("name") or ""
        file_attr = tc.get("file") or ""
        time = tc.get("time") or "0"
        st = status_of(tc)
        msg_raw = message_of(tc)
        pkg = package_of(file_attr) or classname.split(".")[0]

        totals[st] += 1
        if st in ("failure", "error"):
            by_package[pkg] += 1
            sig = norm_msg(msg_raw)
            by_cluster[sig] += 1
            if len(cluster_examples[sig]) < 3:
                cluster_examples[sig].append((file_attr, name))
        rows.append(
            {
                "test": f"{classname}::{name}" if classname else name,
                "status": st,
                "file": file_attr,
                "class": classname,
                "time": time,
                "message": msg_raw.replace("\n", " ")[:500],
                "package": pkg,
            }
        )

    total = sum(totals.values())
    failed = totals["failure"] + totals["error"]
    print("=" * 80)
    print(
        f"TOTAL TESTS: {total} | FAILED/ERROR: {failed} | SKIPPED: {totals['skipped']} | PASSED: {totals['passed']}"
    )
    if total:
        rate = (failed / total) * 100
        print(f"FAIL RATE: {rate:.1f}%")
    print("=" * 80)

    print("\n🔥 Top failing packages (heatmap):")
    for pkg, cnt in by_package.most_common(args.top):
        bar = "█" * min(40, cnt)
        print(f"{cnt:5d}  {pkg:40s} {bar}")

    print("\n🧩 Top error clusters (normalized messages):")
    for sig, cnt in by_cluster.most_common(args.top):
        print(f"\n[{cnt} failures] {sig or '(no message)'}")
        for f, n in cluster_examples[sig]:
            print(f"    - {f}::{n}")

    out_csv = Path("triage_summary.csv")
    with out_csv.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "test",
                "status",
                "file",
                "class",
                "time",
                "message",
                "package",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote CSV: {out_csv.resolve()}")


if __name__ == "__main__":
    sys.exit(main())
