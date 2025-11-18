# Build stage
FROM golang:1.20-alpine AS builder

WORKDIR /app

COPY go.mod go.sum ./
RUN go mod download

COPY . .

RUN CGO_ENABLED=0 GOOS=linux go build -o iptv-proxy ./cmd/iptv-proxy

# Final image
FROM alpine:3

WORKDIR /root/

COPY --from=builder /app/iptv-proxy .
COPY users.json users.json

EXPOSE 10000

CMD ["./iptv-proxy"]
