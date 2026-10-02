# syntax=docker/dockerfile:1
# dev     — прогон тестов в CI, без прод-зависимостей NPU
# runtime — образ, который публикуется в GHCR

FROM debian:bookworm-slim AS dev

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip python3-venv ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-dev.txt /tmp/
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements-dev.txt

ENV PATH=/opt/venv/bin:${PATH}
WORKDIR /app
CMD ["./scripts/ci-test.sh"]

FROM debian:bookworm-slim AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv ca-certificates curl libgomp1 libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

# BOARD — плата в теге образа (rk3588). Следующая плата — новая запись в app/npu_libs.py и в матрице CI.
ARG TARGETARCH
ARG BOARD=rk3588
ENV PATH=/opt/venv/bin:${PATH} \
    PORT=8080 \
    PYTHONUNBUFFERED=1 \
    MODELS_DIR=/models \
    MODELS=laya,kev \
    SYSTEM_ONE_ENGINE=npu \
    BOARD=${BOARD} \
    RKNN_LIB=/opt/npu/librknnrt-2.3.2.so \
    RKLLM_LIB=/opt/npu/librkllmrt-1.3.1.so
LABEL org.opencontainers.image.version=${BOARD}

COPY app/npu_libs.py /tmp/npu_libs.py
RUN arch="${TARGETARCH:-}"; \
    if [ -z "$arch" ]; then arch="$(dpkg --print-architecture)"; fi; \
    python /tmp/npu_libs.py "$BOARD" "$arch" /opt/npu \
    && rm -f /tmp/npu_libs.py

WORKDIR /app
COPY app /app/app
COPY scripts/healthcheck.sh /app/healthcheck.sh
RUN chmod +x /app/healthcheck.sh

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=600s --retries=30 \
    CMD ["/app/healthcheck.sh"]

CMD ["python", "-m", "app.server"]
