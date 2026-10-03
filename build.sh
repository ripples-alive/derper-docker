#!/bin/sh

NAME=derper
BUILDER="${NAME}-builder"
SCRIPT_DIR=$(CDPATH=; cd -- "$(dirname -- "$0")" && pwd)
VERSION=$(tr -d '\r\n' <"$SCRIPT_DIR/tailscale-version.txt")

docker buildx create --use --name "$BUILDER"
docker buildx inspect --bootstrap

docker buildx build \
    --platform linux/amd64,linux/arm64 \
    --push \
    --pull \
    --tag "ripples/$NAME:$VERSION" \
    --build-arg "VERSION=$VERSION" \
    --builder "$BUILDER" .

docker buildx stop "$BUILDER"
docker buildx rm "$BUILDER"
