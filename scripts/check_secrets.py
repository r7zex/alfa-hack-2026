"""High-confidence credential-shape check over tracked source (not a full audit)."""
import re
import subprocess
from pathlib import Path

patterns=[re.compile(p) for p in [
    rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    rb'\bAKIA[0-9A-Z]{16}\b',rb'\bgh[pousr]_[A-Za-z0-9]{30,}\b',
    rb'\bgithub_pat_[A-Za-z0-9_]{50,}\b',rb'\bsk-proj-[A-Za-z0-9_-]{40,}\b',
]]
bad=[]
for filename in subprocess.check_output(['git','ls-files','-z']).decode().split('\0'):
    path=Path(filename)
    if path.is_file() and path.stat().st_size<2_000_000 and any(p.search(path.read_bytes()) for p in patterns):bad.append(filename)
if bad:raise SystemExit('Credential-shaped values in: '+', '.join(bad))
print('Tracked-source credential-shape check passed')
