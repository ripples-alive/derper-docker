#!/usr/bin/env python3
"""Check the public GHCR artifacts before treating a release as published."""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

ACCEPT = ", ".join(
    (
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    )
)
PLATFORMS = {("linux", "amd64"), ("linux", "arm64")}


def version_parts(version: str) -> tuple[int, ...]:
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("expected a stable version without a v prefix")
    return tuple(map(int, version.split(".")))


class Registry:
    def __init__(self, image: str):
        match = re.fullmatch(r"ghcr\.io/([a-z0-9_.-]+/[a-z0-9_./-]+)", image)
        if not match or ".." in image:
            raise ValueError("expected a public GHCR image path without a tag")
        self.repository = match.group(1)
        query = urllib.parse.urlencode({"service": "ghcr.io", "scope": f"repository:{self.repository}:pull"})
        with urllib.request.urlopen(f"https://ghcr.io/token?{query}", timeout=30) as response:
            self.token = json.load(response)["token"]

    def manifest(self, tag: str) -> tuple[str, dict] | None:
        request = urllib.request.Request(
            f"https://ghcr.io/v2/{self.repository}/manifests/{tag}",
            headers={"Accept": ACCEPT, "Authorization": f"Bearer {self.token}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                digest = response.headers.get("Docker-Content-Digest", "")
                if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
                    raise RuntimeError("registry did not return a valid manifest digest")
                return digest, json.load(response)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            raise RuntimeError(f"registry manifest request returned HTTP {error.code}") from None


def published(registry, version: str) -> bool:
    version_parts(version)
    release = registry.manifest(version)
    if release is None:
        return False
    digest, manifest = release
    platforms = {
        (entry.get("platform", {}).get("os"), entry.get("platform", {}).get("architecture"))
        for entry in manifest.get("manifests", [])
    }
    if not PLATFORMS <= platforms:
        return False
    latest = registry.manifest("latest")
    return latest is not None and latest[0] == digest


def needs_update(current: str, candidate: str, image: str) -> bool:
    current_parts, candidate_parts = version_parts(current), version_parts(candidate)
    if candidate_parts < current_parts:
        raise ValueError(f"refusing downgrade from {current} to {candidate}")
    if candidate_parts > current_parts:
        return True
    # A previous run may have merged the version PR and then failed to publish.
    return not published(Registry(image), candidate)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["needs-update", "verify"])
    parser.add_argument("--image", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--current")
    args = parser.parse_args()
    if args.mode == "needs-update":
        if not args.current:
            parser.error("--current is required for needs-update")
        print("true" if needs_update(args.current, args.version, args.image) else "false")
        return
    registry = Registry(args.image)
    for attempt in range(5):
        if published(registry, args.version):
            print("Version and latest tags resolve to the same amd64/arm64 image index.")
            return
        if attempt < 4:
            time.sleep(3)
    raise SystemExit("Published image verification failed: missing platforms, version tag, or matching latest tag")


if __name__ == "__main__":
    main()
