#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def _state_path() -> Path:
    return Path(os.environ["FAKE_GH_STATE"])


def _load() -> list[dict[str, object]]:
    value = json.loads(_state_path().read_text(encoding="utf-8"))
    assert isinstance(value, list)
    return value


def _save(value: list[dict[str, object]]) -> None:
    _state_path().write_text(json.dumps(value), encoding="utf-8")


def _log() -> None:
    path = Path(os.environ["FAKE_GH_LOG"])
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(sys.argv[1:]) + "\n")


def _option(name: str) -> str:
    index = sys.argv.index(name)
    return sys.argv[index + 1]


def _counter() -> int:
    path = Path(os.environ["FAKE_GH_COUNTER"])
    value = int(path.read_text(encoding="utf-8")) + 1 if path.exists() else 1
    path.write_text(str(value), encoding="utf-8")
    return value


def _settle(state: list[dict[str, object]]) -> None:
    threshold = int(os.environ.get("FAKE_IMMUTABLE_AFTER", "0"))
    if not threshold or _counter() < threshold:
        return
    for release in state:
        if release["draft"] is False:
            release["immutable"] = True
    _save(state)


def _api() -> None:
    target = sys.argv[-1]
    if "releases?" in target:
        _list_releases(target)
    elif "/git/ref/tags/" in target:
        print(json.dumps({"object": {"type": "commit", "sha": os.environ["FAKE_TAG_SHA"]}}))
    elif "/releases/assets/" in target:
        _delete_asset(int(target.rsplit("/", 1)[1]))
    else:
        raise AssertionError(target)


def _list_releases(target: str) -> None:
    state = _load()
    _settle(state)
    query = parse_qs(urlparse(target).query)
    page = int(query.get("page", ["1"])[0])
    start = (page - 1) * 100
    print(json.dumps(state[start : start + 100]))


def _delete_asset(asset_id: int) -> None:
    state = _load()
    release = state[0]
    assets = release["assets"]
    assert isinstance(assets, list)
    release["assets"] = [asset for asset in assets if asset["id"] != asset_id]
    _save(state)


def _create() -> None:
    release = {
        "id": 1,
        "tag_name": sys.argv[3],
        "name": _option("--title"),
        "body": _option("--notes"),
        "prerelease": "--prerelease" in sys.argv,
        "draft": True,
        "immutable": False,
        "assets": [],
    }
    _save([release])


def _asset(path: Path, asset_id: int) -> dict[str, object]:
    data = path.read_bytes()
    return {
        "id": asset_id,
        "name": path.name,
        "state": "uploaded",
        "size": len(data),
        "digest": f"sha256:{hashlib.sha256(data).hexdigest()}",
    }


def _upload() -> None:
    state = _load()
    release = state[0]
    assets = release["assets"]
    assert isinstance(assets, list)
    source = Path(sys.argv[4])
    assets.append(_asset(source, len(assets) + 100))
    upload = Path(os.environ["FAKE_GH_UPLOADS"]) / source.name
    upload.write_bytes(source.read_bytes())
    _save(state)


def _publish() -> None:
    state = _load()
    state[0]["draft"] = False
    state[0]["immutable"] = os.environ.get("FAKE_IMMUTABLE_AFTER") is None
    _save(state)


def _verify() -> None:
    if os.environ.get("FAKE_VERIFY_FAILURE"):
        raise SystemExit(1)


def main() -> None:
    _log()
    if sys.argv[1] == "api":
        _api()
    elif sys.argv[1:3] == ["release", "create"]:
        _create()
    elif sys.argv[1:3] == ["release", "upload"]:
        _upload()
    elif sys.argv[1:3] == ["release", "edit"]:
        _publish()
    elif sys.argv[1:3] in (["release", "verify"], ["release", "verify-asset"]):
        _verify()
    else:
        raise AssertionError(sys.argv[1:])


if __name__ == "__main__":
    main()
