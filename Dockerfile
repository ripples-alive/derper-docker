FROM golang:1.23-alpine AS builder

WORKDIR /go/src/tailscale

ARG VERSION

RUN mkdir -p /go/src && cd /go/src \
    && wget -O tailscale.tar.gz https://github.com/tailscale/tailscale/archive/refs/tags/v$VERSION.tar.gz \
    && tar -xzvf tailscale.tar.gz -C tailscale --strip-components 1 \
    && rm tailscale.tar.gz

RUN go build ./cmd/derper && go build ./cmd/derpprobe

FROM alpine:3.19

WORKDIR /app

COPY --from=builder /go/src/tailscale/derper .
COPY --from=builder /go/src/tailscale/derpprobe .

CMD /app/derper
