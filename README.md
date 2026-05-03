# derper Docker image

This repository builds a multi-architecture Docker image for Tailscale DERP
server binaries `derper` and `derpprobe`.

Images are published to GitHub Container Registry:

- `ghcr.io/ripples-alive/derper:1.96.4`
- `ghcr.io/ripples-alive/derper:latest`

The image supports `linux/amd64` and `linux/arm64`.

## Usage

```sh
docker run --rm \
  -p 443:443 \
  -p 80:80 \
  ghcr.io/ripples-alive/derper:1.96.4
```

Pass `derper` flags after the image name as needed:

```sh
docker run --rm \
  -p 443:443 \
  -p 80:80 \
  ghcr.io/ripples-alive/derper:1.96.4 \
  --hostname derp.example.com
```

## Builds

Local builds use `build.sh`, which pushes `ripples/derper:1.96.4` to Docker
Hub for `linux/amd64` and `linux/arm64`.

GitHub Actions builds the same Dockerfile directly with Buildx and the build
argument `VERSION=1.96.4`. The workflow publishes
`ghcr.io/ripples-alive/derper:1.96.4` and `ghcr.io/ripples-alive/derper:latest`
on pushes to `main`, version tags such as `v1.96.4`, and manual
`workflow_dispatch` runs. Pull requests build the image for validation but do
not publish it.

To change the Tailscale source version used by GitHub Actions, update
`DEFAULT_TAILSCALE_VERSION` in `.github/workflows/docker-image.yml`.
