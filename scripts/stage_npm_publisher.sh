#!/usr/bin/env bash
set -euo pipefail

destination="${1:-dist/publish-tools}"
archive="npm-12.0.2.tgz"
expected="b885e890b9418fa1693544d05f53e64f9a73ec194837d4258b15fecdd692347b1dd2a517b1b0cbaf9d31cd8e92c3b70956bd2ecc72833a57b4b3098f5bfa7943"
rm -rf -- "$destination"
mkdir -p -- "$destination"
npm pack npm@12.0.2 --silent --pack-destination "$destination" >/dev/null
python3 - "$destination/$archive" "$expected" <<'PY'
import hashlib
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
if hashlib.sha512(path.read_bytes()).hexdigest() != sys.argv[2]:
    raise SystemExit("npm publisher checksum mismatch")
PY
