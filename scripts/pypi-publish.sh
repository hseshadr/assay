#!/usr/bin/env bash
{ set +x; } 2>/dev/null
unset PS4
set -euo pipefail

readonly PYPI_UPLOAD_URL="https://upload.pypi.org/legacy/"
readonly PYPI_CHECK_URL="https://pypi.org/simple/"
readonly POLL_ATTEMPTS=6
readonly POLL_SECONDS=2

script_dir="$(cd -- "${BASH_SOURCE[0]%/*}" && pwd -P)"
repo_root="$(cd -- "$script_dir/.." && pwd -P)"
verifier="$repo_root/scripts/verify_release_artifacts.py"
publish=false
artifact_root=""
runtime_root=""
snapshot_root=""
pypi_token="${HARISH_PYPI_TOKEN-}"
unset HARISH_PYPI_TOKEN HARISH_NPM_TOKEN PYPI_API_TOKEN NPM_TOKEN
unset UV_PUBLISH_TOKEN UV_PUBLISH_USERNAME UV_PUBLISH_PASSWORD
unset UV_PUBLISH_URL UV_PUBLISH_CHECK_URL UV_PUBLISH_INDEX UV_KEYRING_PROVIDER

usage() {
  echo "usage: scripts/pypi-publish.sh [--publish] [ARTIFACT_ROOT]" >&2
}

die() {
  echo "$1" >&2
  exit 1
}

cleanup() {
  [[ -z "$runtime_root" ]] || rm -rf -- "$runtime_root"
}

trap cleanup EXIT HUP INT TERM

parse_arguments() {
  local argument
  for argument in "$@"; do
    case "$argument" in
      --publish) publish=true ;;
      -*) usage; exit 2 ;;
      *) [[ -z "$artifact_root" ]] || { usage; exit 2; }; artifact_root="$argument" ;;
    esac
  done
  artifact_root="${artifact_root:-$repo_root/dist/release}"
}

reject_unsafe_tree() {
  local root="$1" listing="$2" entry
  [[ -d "$root" && ! -L "$root" ]] || die "release root is a symlink or nonregular"
  /usr/bin/find "$root" -mindepth 1 -print0 >"$listing"
  while IFS= read -r -d '' entry; do
    [[ ! -L "$entry" && ( -d "$entry" || -f "$entry" ) ]] ||
      die "release envelope contains a symlink or nonregular member"
  done <"$listing"
}

initialize_snapshot() {
  umask 077
  runtime_root="$(mktemp -d "${TMPDIR:-/tmp}/assay-pypi-publish.XXXXXX")"
  runtime_root="$(cd -- "$runtime_root" && pwd -P)"
  chmod 700 "$runtime_root"
  snapshot_root="$runtime_root/release"
  mkdir -m 700 "$snapshot_root"
  reject_unsafe_tree "$artifact_root" "$runtime_root/source-members"
  cp -R -- "$artifact_root/." "$snapshot_root/"
  reject_unsafe_tree "$snapshot_root" "$runtime_root/snapshot-members"
}

verify_snapshot() {
  python3 "$verifier" "$snapshot_root"
}

select_artifacts() {
  local wheels sdists wheel_name sdist_name
  shopt -s nullglob
  wheels=("$snapshot_root"/python/assay_engine-*-py3-none-any.whl)
  sdists=("$snapshot_root"/python/assay_engine-*.tar.gz)
  [[ ${#wheels[@]} -eq 1 && ${#sdists[@]} -eq 1 ]] || die "expected one Assay wheel and sdist"
  wheel="${wheels[0]}"
  sdist="${sdists[0]}"
  wheel_name="${wheel##*/assay_engine-}"
  python_version="${wheel_name%-py3-none-any.whl}"
  sdist_name="${sdist##*/assay_engine-}"
  [[ "${sdist_name%.tar.gz}" == "$python_version" ]] || die "Python artifact versions differ"
}

validate_version() {
  local number='(0|[1-9][0-9]*)'
  [[ "$python_version" =~ ^${number}\.${number}\.${number}(\.dev${number})?$ ]] ||
    die "malformed Python version: $python_version"
  pypi_api="https://pypi.org/pypi/assay-engine/$python_version/json"
}

fetch_metadata() {
  curl --silent --show-error --output "$metadata_file" --write-out '%{http_code}' \
    --connect-timeout 5 --max-time 20 --max-filesize 1048576 "$pypi_api"
}

verify_metadata() {
  python3 - "$metadata_file" "$snapshot_root/python" "$python_version" <<'PY'
import hashlib
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
root = pathlib.Path(sys.argv[2])
expected = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in root.iterdir()}
records = payload.get("urls", [])
actual = {item["filename"]: item["digests"]["sha256"] for item in records}
identity = (payload.get("info", {}).get("name"), payload.get("info", {}).get("version"))
if len(records) != len(actual) or identity != ("assay-engine", sys.argv[3]) or actual != expected:
    raise SystemExit(f"assay-engine {sys.argv[3]} registry bytes conflict with reviewed artifacts")
PY
}

check_registry() {
  local status
  status="$(fetch_metadata)" || die "PyPI registry check failed"
  case "$status" in
    404) registry_state="missing" ;;
    200) verify_metadata; registry_state="exact" ;;
    *) die "PyPI registry check failed with HTTP $status" ;;
  esac
}

uv_publish() {
  local dry_run="$1"
  local -a arguments=(publish)
  [[ "$dry_run" == false ]] || arguments+=(--dry-run)
  uv "${arguments[@]}" --no-config --no-progress --trusted-publishing never --keyring-provider \
    disabled --publish-url "$PYPI_UPLOAD_URL" --check-url "$PYPI_CHECK_URL" "$wheel" "$sdist"
}

print_plan() {
  echo "PLAN only; no registry mutation. Checked assay-engine $python_version on PyPI."
  echo "A PyPI account-wide API token can bootstrap assay-engine; export HARISH_PYPI_TOKEN in the caller only with --publish."
  echo "Real releases should use the GitHub Actions OIDC workflow for PEP 740 provenance."
}

run_plan() {
  if [[ "$registry_state" == exact ]]; then
    echo "PyPI already serves the reviewed assay-engine $python_version bytes; no mutation needed."
  else
    uv_publish true
    print_plan
  fi
}

poll_pypi() {
  local attempt status
  for ((attempt = 1; attempt <= POLL_ATTEMPTS; attempt++)); do
    status="$(fetch_metadata)" || die "PyPI post-publish check failed"
    if [[ "$status" == 200 ]]; then verify_metadata; return; fi
    [[ "$status" == 404 && $attempt -lt $POLL_ATTEMPTS ]] ||
      die "PyPI publication did not become authoritative"
    sleep "$POLL_SECONDS"
  done
}

run_publish() {
  [[ "$registry_state" == missing ]] || { run_plan; return; }
  [[ -n "$pypi_token" ]] || die "HARISH_PYPI_TOKEN is required with --publish"
  [[ "$pypi_token" != *$'\n'* && "$pypi_token" != *$'\r'* ]] ||
    die "HARISH_PYPI_TOKEN is malformed"
  UV_PUBLISH_TOKEN="$pypi_token" uv_publish false
  poll_pypi
  echo "Verified PyPI serves the reviewed filenames and hashes for assay-engine $python_version."
  echo "Future real releases should use the GitHub Actions OIDC workflow for provenance."
}

wheel=""
sdist=""
python_version=""
pypi_api=""
metadata_file=""
registry_state=""
parse_arguments "$@"
initialize_snapshot
metadata_file="$runtime_root/pypi.json"
verify_snapshot
select_artifacts
validate_version
check_registry
if [[ "$publish" == true ]]; then run_publish; else run_plan; fi
