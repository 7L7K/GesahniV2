# parse_results.py
import re, csv

with open("test_results_9_8_815pm.txt") as f, open("tests_summary.csv", "w", newline="") as out:
    writer = csv.writer(out)
    writer.writerow(["Test", "Status"])
    for line in f:
        m = re.match(r"(PASSED|FAILED|SKIPPED|ERROR)\s+(.*)", line.strip())
        if m:
            writer.writerow([m.group(2), m.group(1)])
