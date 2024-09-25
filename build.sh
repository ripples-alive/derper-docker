#!/bin/sh

VERSION=1.74.1

docker build . -t ripples/derper:$VERSION --build-arg VERSION=$VERSION
docker push ripples/derper:$VERSION
