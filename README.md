# derper Docker image

This repository builds a multi-architecture Docker image for Tailscale DERP
server binaries `derper` and `derpprobe`.

Images are published to GitHub Container Registry:

- `ghcr.io/ripples-alive/derper:1.98.8`
- `ghcr.io/ripples-alive/derper:latest`

The image supports `linux/amd64` and `linux/arm64`.

## Usage

```sh
docker run --rm \
  -p 443:443 \
  -p 80:80 \
  ghcr.io/ripples-alive/derper:1.98.8
```

Pass `derper` flags after the image name as needed:

```sh
docker run --rm \
  -p 443:443 \
  -p 80:80 \
  ghcr.io/ripples-alive/derper:1.98.8 \
  --hostname derp.example.com
```

## Builds

Local builds use `build.sh`, which pushes `ripples/derper:1.98.8` to Docker
Hub for `linux/amd64` and `linux/arm64`.

GitHub Actions builds the same Dockerfile directly with Buildx and the build
argument `VERSION=1.98.8`. The workflow publishes
`ghcr.io/ripples-alive/derper:1.98.8` and `ghcr.io/ripples-alive/derper:latest`
on pushes to `main`, version tags such as `v1.98.8`, and manual
`workflow_dispatch` runs. Pull requests build the image for validation but do
not publish it.

To change the Tailscale source version used by local builds and GitHub Actions,
update `tailscale-version.txt`. Automated version commits intentionally avoid
workflow files so the built-in `GITHUB_TOKEN` can push them.

The `Update Tailscale stable release` workflow checks the upstream stable
release every day, validates a candidate multi-architecture build, and opens
an exact-version PR for automatic merging when repository rules allow it.
