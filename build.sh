#!/bin/sh

BUILDER=derper-builder
VERSION=1.80.0

docker buildx create --use --name $BUILDER
docker buildx inspect --bootstrap

docker buildx build \
    --platform linux/amd64,linux/arm64 \
    --output "type=image,push=true" \
    --tag ripples/derper:$VERSION \
    --build-arg VERSION=$VERSION \
    --builder $BUILDER .

docker buildx stop $BUILDER
docker buildx rm $BUILDER

