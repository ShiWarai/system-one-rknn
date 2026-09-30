# syntax=docker/dockerfile:1
# dev     — прогон тестов в CI, без прод-зависимостей
# runtime — образ, который публикуется в GHCR
# Замените target runtime: уберите stub-server.sh и поставьте свой CMD.

FROM debian:bookworm-slim AS dev

WORKDIR /app
COPY scripts/ci-test.sh /app/scripts/ci-test.sh
RUN chmod +x /app/scripts/ci-test.sh
CMD ["./scripts/ci-test.sh"]

FROM debian:bookworm-slim AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends busybox curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY scripts/stub-server.sh /app/stub-server.sh
COPY scripts/healthcheck.sh /app/healthcheck.sh
RUN chmod +x /app/stub-server.sh /app/healthcheck.sh

ENV PORT=8080
EXPOSE 8080

HEALTHCHECK --interval=5s --timeout=3s --retries=5 \
    CMD ["/app/healthcheck.sh"]

CMD ["/app/stub-server.sh"]
