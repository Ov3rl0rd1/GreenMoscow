FROM debian:bookworm-slim AS libredwg

ARG LIBREDWG_VERSION=0.14.8597

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        autoconf \
        automake \
        build-essential \
        ca-certificates \
        git \
        libtool \
        pkg-config \
        python3 \
        texinfo \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --branch ${LIBREDWG_VERSION} https://github.com/LibreDWG/libredwg.git /src/libredwg

WORKDIR /src/libredwg

RUN sh autogen.sh \
    && ./configure --prefix=/opt/libredwg --disable-bindings --disable-shared --disable-dependency-tracking \
    && make -j"$(nproc)" \
    && make install \
    && strip /opt/libredwg/bin/dwg2dxf


FROM python:3.11-slim AS engine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg \
    GREENPLAN_KNOWLEDGE_ROOT=/app/knowledge \
    GREENPLAN_DWG2DXF=/usr/local/bin/dwg2dxf \
    GREENPLAN_JOBS_ROOT=/data/jobs \
    GREENPLAN_CACHE_DIR=/data/cache

WORKDIR /app

COPY --from=libredwg /opt/libredwg/bin/dwg2dxf /usr/local/bin/dwg2dxf
COPY engine /app/engine
COPY knowledge /app/knowledge

RUN pip install --no-cache-dir /app/engine \
    && useradd --create-home --uid 10001 greenplan \
    && mkdir -p /data/jobs /data/cache \
    && chown -R greenplan:greenplan /data

USER greenplan

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz').read()"

CMD ["uvicorn", "--factory", "greenplan.api.app:create_app_from_environment", "--host", "0.0.0.0", "--port", "8000"]
