#!/usr/bin/env python3
"""Check repository-relative Markdown/HTML links without network access."""
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
errors = []
checked = 0
files = [ROOT / 'README.md', ROOT / 'CONTRIBUTING.md', ROOT / 'SECURITY.md', *sorted((ROOT / 'docs').rglob('*.md'))]
for source in files:
    text = re.sub(r'```.*?```', '', source.read_text(), flags=re.S)
    links = re.findall(r'!?\[[^\]]*\]\(([^)]+)\)', text)
    links += re.findall(r'(?:href|src)="([^"]+)"', text)
    for raw in links:
        href = raw.strip().strip('<>')
        parsed = urlsplit(href)
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        target = (source.parent / unquote(parsed.path)).resolve()
        if not target.is_relative_to(ROOT) or not target.exists():
            errors.append(f'{source.relative_to(ROOT)}: missing {href}')
        checked += 1
if errors:
    raise SystemExit('\n'.join(errors))
print(f'OK: {checked} local links across {len(files)} documents')
