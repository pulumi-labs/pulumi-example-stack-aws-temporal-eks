FROM ghcr.io/astral-sh/uv:0.9.10@sha256:29bd45092ea8902c0bbb7f0a338f0494a382b1f4b18355df5be270ade679ff1d AS uv
FROM python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c
COPY --from=uv /uv /usr/local/bin/uv
COPY worker/requirements.lock /opt/requirements.lock
COPY wheelhouse/ /opt/wheelhouse/
RUN uv pip install --system --no-index --find-links /opt/wheelhouse \
    --require-hashes --only-binary :all: -r /opt/requirements.lock \
    && rm -rf /opt/wheelhouse
WORKDIR /app
COPY --chown=1000:1000 worker/*.py /app/worker/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 1000:1000
ENTRYPOINT ["python", "-m", "worker.main"]
