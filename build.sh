#!/bin/sh

VERSION=1.76.6

docker build . -t ripples/derper:$VERSION --build-arg VERSION=$VERSION
docker push ripples/derper:$VERSION
