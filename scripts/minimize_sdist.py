"""Remove Hatchling's forced VCS control file from the minimal release sdist."""

from __future__ import annotations

import gzip
import os
import sys
import tarfile
from pathlib import Path
from tempfile import NamedTemporaryFile

_ARGUMENT_COUNT = 2


def _normalized(member: tarfile.TarInfo, epoch: int) -> tarfile.TarInfo:
    member.uid = 0
    member.gid = 0
    member.uname = ""
    member.gname = ""
    member.mtime = epoch
    member.pax_headers = {}
    return member


def _copy_members(source: tarfile.TarFile, destination: tarfile.TarFile, epoch: int) -> int:
    removed = 0
    for member in source.getmembers():
        if Path(member.name).name == ".gitignore":
            removed += 1
            continue
        stream = source.extractfile(member) if member.isfile() else None
        destination.addfile(_normalized(member, epoch), stream)
    return removed


def minimize(path: Path, epoch: int) -> None:
    """Rewrite one sdist reproducibly while removing only its root .gitignore."""
    with (
        NamedTemporaryFile(dir=path.parent, delete=False) as output,
        gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=epoch) as compressed,
        tarfile.open(path, "r:gz") as source,
        tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as destination,
    ):
        temporary = Path(output.name)
        removed = _copy_members(source, destination, epoch)
    if removed != 1:
        temporary.unlink(missing_ok=True)
        raise ValueError("sdist VCS member mismatch")
    os.replace(temporary, path)


def main() -> int:
    if len(sys.argv) != _ARGUMENT_COUNT:
        print("usage: minimize_sdist.py SDIST", file=sys.stderr)
        return 1
    minimize(Path(sys.argv[1]), int(os.environ["SOURCE_DATE_EPOCH"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
