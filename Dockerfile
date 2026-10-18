# syntax=docker/dockerfile:1
# dev         — прогон тестов в CI; torch нужен, чтобы импортировать CPU-движки (без CUDA)
# runtime     — NPU-образ для плат, публикуется в GHCR
# runtime-cpu — CPU-образ без NPU (SYSTEM_ONE_ENGINE=cpu), публикуется в GHCR

FROM debian:bookworm-slim AS dev

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip python3-venv ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-dev.txt /tmp/
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu torch==2.14.1+cpu \
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

# BOARD — семейство образа в теге: rknn (NPU-рантаймы RK3588, см. app/npu_libs.py). Следующее — новая запись и строка матрицы CI.
ARG TARGETARCH
ARG BOARD=rknn
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

FROM debian:bookworm-slim AS runtime-cpu

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv ca-certificates curl libgomp1 libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-cpu.txt /tmp/
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu torch==2.14.1+cpu \
    && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements-cpu.txt

ENV PATH=/opt/venv/bin:${PATH} \
    PORT=8080 \
    PYTHONUNBUFFERED=1 \
    MODELS_DIR=/models \
    MODELS=laya,kev \
    SYSTEM_ONE_ENGINE=cpu \
    HF_HOME=/models/hf

WORKDIR /app
COPY app /app/app
COPY scripts/healthcheck.sh /app/healthcheck.sh
RUN chmod +x /app/healthcheck.sh

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=600s --retries=30 \
    CMD ["/app/healthcheck.sh"]

CMD ["python", "-m", "app.server"]
