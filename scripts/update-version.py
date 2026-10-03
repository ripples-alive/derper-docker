#!/usr/bin/env python3
"""Read and update the pinned upstream release version.

The version is kept in a regular repository file so automated update commits
do not need permission to modify GitHub workflow files.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
SEMVER_RE = re.compile(r"(?<!\d)\d+\.\d+\.\d+(?!\d)")


def validate(version: str) -> tuple[int, int, int]:
    if not VERSION_RE.fullmatch(version):
        raise ValueError(f"unsupported version: {version!r}")
    return tuple(int(part) for part in version.split("."))  # type: ignore[return-value]


def read_current(root: Path, version_file: str) -> str:
    path = root / version_file
    raw = path.read_text(encoding="utf-8")
    version = raw.strip()
    validate(version)
    if raw != f"{version}\n":
        raise ValueError(f"{path} must contain exactly one version and a newline")

    readme = (root / "README.md").read_text(encoding="utf-8")
    versions = set(SEMVER_RE.findall(readme))
    if versions != {version}:
        found = ", ".join(sorted(versions)) or "none"
        raise ValueError(
            f"version drift in README.md: expected {version}, found {found}"
        )
    return version


def update(root: Path, version_file: str, new_version: str) -> bool:
    new_parts = validate(new_version)
    current = read_current(root, version_file)
    if new_parts < validate(current):
        raise ValueError(f"refusing to downgrade from {current} to {new_version}")
    if new_version == current:
        return False

    (root / version_file).write_text(f"{new_version}\n", encoding="utf-8")
    readme_path = root / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    readme, count = re.subn(rf"(?<!\d){re.escape(current)}(?!\d)", new_version, readme)
    if count < 1:
        raise ValueError("README.md did not contain the current version")
    readme_path.write_text(readme, encoding="utf-8")

    if read_current(root, version_file) != new_version:
        raise ValueError("version update left the repository inconsistent")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--version-file", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--current", action="store_true")
    group.add_argument("--set", dest="new_version", metavar="VERSION")
    args = parser.parse_args()

    try:
        if args.current:
            print(read_current(args.root, args.version_file))
        else:
            print(
                "updated"
                if update(args.root, args.version_file, args.new_version)
                else "unchanged"
            )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
