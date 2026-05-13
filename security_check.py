"""
Security check script for Lapwing
Prevents accidental commit of secrets
"""
import re
import sys
from pathlib import Path


def check_file_for_secrets(filepath: Path) -> list:
    """Check a file for potential secrets"""
    issues = []

    # Skip certain files/directories
    skip_patterns = [
        'open-llm-vtuber',  # Third-party code
        'test',
        'example',
        'demo',
    ]
    if any(p in str(filepath).lower() for p in skip_patterns):
        return []

    # Patterns to detect
    patterns = [
        (r'sk-[a-zA-Z0-9]{32,}', 'API Key'),
        (r'api[_-]?key\s*=\s*["\'][^"\']{20,}["\']', 'API Key assignment'),
        (r'secret\s*=\s*["\'][^"\']{10,}["\']', 'Secret assignment'),
        (r'token\s*=\s*["\'][^"\']{10,}["\']', 'Token assignment'),
        (r'password\s*=\s*["\'][^"\']{6,}["\']', 'Password assignment'),
    ]

    # Safe patterns (placeholders)
    safe_patterns = [
        r'your-',
        r'placeholder',
        r'example',
        r'test',
        r'demo',
        r'fake',
        r'mock',
        r'not-needed',
        r'\*',  # Poetry uses * for dependencies
    ]

    try:
        content = filepath.read_text(encoding='utf-8')
        for pattern, desc in patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                matched_text = match.group()

                # Check if it's safe
                if any(re.search(safe, matched_text, re.IGNORECASE) for safe in safe_patterns):
                    continue

                line_num = content[:match.start()].count('\n') + 1
                issues.append(f"{filepath}:{line_num}: Potential {desc}")
    except Exception:
        pass  # Skip files that can't be read

    return issues


def main():
    """Main security check"""
    print("Lapwing Security Check")
    print("=" * 50)

    # Files to check
    check_paths = [
        Path("."),
    ]

    # Files to ignore
    ignore_patterns = [
        '.git',
        '__pycache__',
        'node_modules',
        '.env',  # .env is allowed but should be in .gitignore
        '*.pyc',
    ]

    all_issues = []

    for path in check_paths:
        if path.is_file():
            issues = check_file_for_secrets(path)
            all_issues.extend(issues)
        elif path.is_dir():
            for file in path.rglob('*'):
                # Skip ignored patterns
                if any(p in str(file) for p in ignore_patterns):
                    continue
                if file.is_file() and file.suffix in ['.py', '.json', '.yaml', '.yml', '.toml', '.txt']:
                    issues = check_file_for_secrets(file)
                    all_issues.extend(issues)

    if all_issues:
        print("\nPotential secrets found:")
        for issue in all_issues:
            print(f"  - {issue}")
        print("\nSecurity check FAILED")
        print("\nMake sure:")
        print("  1. .env is in .gitignore")
        print("  2. No hardcoded secrets in source files")
        print("  3. Use .env.example for templates")
        sys.exit(1)
    else:
        print("\nNo secrets detected in source files")
        print("\nSecurity check PASSED")
        print("\nReminder:")
        print("  - .env file is ignored by git")
        print("  - Use .env.example as template")
        print("  - Never commit real API keys")


if __name__ == "__main__":
    main()
