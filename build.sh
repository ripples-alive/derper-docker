#!/bin/sh

NAME=derper
BUILDER=${NAME}-builder
VERSION=1.82.0

docker buildx create --use --name $BUILDER
docker buildx inspect --bootstrap

docker buildx build \
    --platform linux/amd64,linux/arm64 \
    --push \
    --pull \
    --tag ripples/$NAME:$VERSION \
    --build-arg VERSION=$VERSION \
    --builder $BUILDER .

docker buildx stop $BUILDER
docker buildx rm $BUILDER

