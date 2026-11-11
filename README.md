# derper Docker image

This repository builds a multi-architecture Docker image for Tailscale DERP
server binaries `derper` and `derpprobe`.

Images are published to GitHub Container Registry:

- `ghcr.io/ripples-alive/derper:1.104.6`
- `ghcr.io/ripples-alive/derper:latest`

The image supports `linux/amd64` and `linux/arm64`.

## Usage

```sh
docker run --rm \
  -p 443:443 \
  -p 80:80 \
  ghcr.io/ripples-alive/derper:1.104.6
```

Pass `derper` flags after the image name as needed:

```sh
docker run --rm \
  -p 443:443 \
  -p 80:80 \
  ghcr.io/ripples-alive/derper:1.104.6 \
  --hostname derp.example.com
```

## Builds

Local builds use `build.sh`, which pushes `ripples/derper:1.104.6` to Docker
Hub for `linux/amd64` and `linux/arm64`.

GitHub Actions builds the same Dockerfile directly with Buildx and the build
argument `VERSION=1.104.6`. The workflow publishes
`ghcr.io/ripples-alive/derper:1.104.6` and `ghcr.io/ripples-alive/derper:latest`
on pushes to `main`, version tags such as `v1.104.6`, and manual
`workflow_dispatch` runs. Pull requests build the image for validation but do
not publish it.

To change the Tailscale source version used by local builds and GitHub Actions,
update `tailscale-version.txt`. Automated version commits intentionally avoid
workflow files so the built-in `GITHUB_TOKEN` can push them.

The `Update Tailscale stable release` workflow checks the upstream stable
release every day, validates a candidate multi-architecture build, and opens
an exact-version PR for automatic merging when repository rules allow it.
It explicitly dispatches validation for that PR's exact commit and waits for
success before merging. This avoids depending on approval-gated workflow events
from bot-created PRs while preserving the repository's merge rules.

The build enables Go's automatic toolchain selection. The selected upstream
source's `go.mod` determines whether a newer compiler must be downloaded;
the base image's bundled compiler does not cap the supported Tailscale release.
Build logs record the actual compiler, and module files remain read-only.

A release is complete only when its version tag contains both target
architectures and `latest` resolves to the same image index. The updater retries
publication when the version file is already current but these artifacts are
missing or inconsistent. A failed push therefore cannot be mistaken for a
successful release on the next scheduled check.

## Failure notifications

`Workflow health alerts` independently watches the stable-release updater,
default-branch image publication, and repository keepalive. A failed or disabled
workflow creates an issue assigned to the repository owner. Set the Actions
variable `WORKFLOW_ALERT_ASSIGNEE` to another GitHub login when needed. The
recipient must enable GitHub web or email notifications for assigned issues.

Repeated failures update the same issue without posting repeated comments.
Recovery closes it; a later failure reopens it. In-flight or cancelled runs do
not clear an existing failure. Pull-request and fork results are ignored, and
manual image-validation runs cannot clear a publication failure.

A daily reconciliation catches missed events and raises an alert if either
daily workflow has not started a run for more than 48 hours. The alert workflow
can also be run manually. It reads current API state, uses only default-branch
code, and copies no build logs into public issues. No external webhook secret is
required. GitHub Actions and GitHub notifications remain shared dependencies;
this does not provide an independent outage monitor or prove email delivery.
