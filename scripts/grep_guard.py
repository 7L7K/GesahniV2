#!/usr/bin/env python3
"""
Grep Guard - Security Pattern Scanner for CI
Scans codebase for sensitive information and security patterns.
"""

import os
import re
import sys
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple

class GrepGuard:
    def __init__(self, root_dir: str = "."):
        self.root_dir = Path(root_dir)
        self.findings = []
        self.stats = {
            "files_scanned": 0,
            "patterns_checked": 0,
            "violations_found": 0
        }

    def get_patterns(self) -> List[Tuple[str, str, str]]:
        """Define security patterns to check for."""
        return [
            # API Keys and Secrets
            (r"sk-[a-zA-Z0-9]{48}", "OpenAI API Key", "HIGH"),
            (r"xox[baprs]-[0-9]+-[0-9]+-[0-9]+-[a-zA-Z0-9]+", "Slack Token", "HIGH"),
            (r"ghp_[a-zA-Z0-9]{36}", "GitHub Personal Access Token", "HIGH"),
            (r"AIza[0-9A-Za-z-_]{35}", "Google API Key", "HIGH"),

            # JWT Secrets
            (r"JWT_SECRET.*=.*[a-zA-Z0-9]{32,}", "JWT Secret", "HIGH"),

            # Database URLs
            (r"postgres://[^:]+:[^@]+@[^\s\"']+", "PostgreSQL Connection String", "HIGH"),
            (r"mysql://[^:]+:[^@]+@[^\s\"']+", "MySQL Connection String", "HIGH"),
            (r"mongodb://[^:]+:[^@]+@[^\s\"']+", "MongoDB Connection String", "HIGH"),

            # Private Keys
            (r"-----BEGIN (RSA|EC|DSA) PRIVATE KEY-----", "Private Key", "CRITICAL"),

            # Hardcoded passwords
            (r"password.*=.*['\"][^'\"]{8,}['\"]", "Hardcoded Password", "HIGH"),
            (r"PASSWORD.*=.*['\"][^'\"]{8,}['\"]", "Hardcoded Password (Env Var)", "HIGH"),

            # AWS Credentials
            (r"AKIA[0-9A-Z]{16}", "AWS Access Key ID", "HIGH"),
            (r"aws_secret_access_key.*=.*['\"][^'\"]{40}['\"]", "AWS Secret Access Key", "HIGH"),

            # Auth Redirect Issues
            (r"redirect_uri.*=.*http://", "HTTP Redirect URI (insecure)", "MEDIUM"),
            (r"window\.location\.href.*=.*javascript:", "JavaScript URL Injection", "HIGH"),

            # CSRF Tokens
            (r"csrf_token.*=.*['\"][^'\"]*['\"]", "CSRF Token Pattern", "LOW"),

            # Session/Cookie Issues
            (r"secure.*=.*false", "Insecure Cookie Setting", "MEDIUM"),
            (r"httpOnly.*=.*false", "Non-HttpOnly Cookie", "MEDIUM"),
        ]

    def scan_file(self, file_path: Path) -> List[Dict]:
        """Scan a single file for security patterns."""
        findings = []

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except (IOError, UnicodeDecodeError):
            return findings

        for pattern, description, severity in self.get_patterns():
            matches = re.findall(pattern, content, re.IGNORECASE | re.MULTILINE)
            if matches:
                for match in matches:
                    # Mask sensitive data
                    masked_match = self.mask_sensitive(match)
                    findings.append({
                        "file": str(file_path.relative_to(self.root_dir)),
                        "pattern": description,
                        "severity": severity,
                        "match": masked_match,
                        "line": self.find_line_number(content, match)
                    })

        return findings

    def find_line_number(self, content: str, match: str) -> int:
        """Find the line number of a match in content."""
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if match in line:
                return i
        return 0

    def mask_sensitive(self, value: str) -> str:
        """Mask sensitive information for safe reporting."""
        if len(value) > 20:
            return value[:8] + "***" + value[-4:]
        return "***"

    def should_scan_file(self, file_path: Path) -> bool:
        """Determine if a file should be scanned."""
        # Skip common non-source files
        skip_patterns = [
            '.git/', '__pycache__/', 'node_modules/', '*.pyc', '*.log',
            '*.min.js', '*.min.css', 'dist/', 'build/', '.env*', '*.lock'
        ]

        file_str = str(file_path)

        for pattern in skip_patterns:
            if pattern in file_str or file_path.match(pattern):
                return False

        # Only scan source files
        extensions = {'.py', '.js', '.ts', '.tsx', '.java', '.go', '.rs', '.php', '.rb', '.yml', '.yaml', '.json', '.md'}
        return file_path.suffix in extensions or file_path.name in ['Dockerfile', 'Makefile']

    def scan_directory(self) -> Dict:
        """Scan the entire directory tree."""
        all_findings = []

        for file_path in self.root_dir.rglob('*'):
            if file_path.is_file() and self.should_scan_file(file_path):
                self.stats["files_scanned"] += 1
                findings = self.scan_file(file_path)
                all_findings.extend(findings)

        self.stats["violations_found"] = len(all_findings)
        self.stats["patterns_checked"] = len(self.get_patterns())

        return {
            "stats": self.stats,
            "findings": all_findings
        }

def main():
    guard = GrepGuard()
    results = guard.scan_directory()

    # Output JSON for CI
    print(json.dumps(results, indent=2))

    # Exit with error if high/critical findings
    critical_high_findings = [
        f for f in results["findings"]
        if f["severity"] in ["CRITICAL", "HIGH"]
    ]

    if critical_high_findings:
        print(f"\n❌ Found {len(critical_high_findings)} critical/high severity issues", file=sys.stderr)
        sys.exit(1)
    else:
        print("\n✅ No critical or high severity security issues found")
        sys.exit(0)

if __name__ == "__main__":
    main()
