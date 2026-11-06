FROM python:3.12-slim AS base
WORKDIR /service
COPY . .
RUN useradd --uid 10001 --create-home service && mkdir /data && chown -R service:service /data /service
ENV STORAGE_ROOT=/data HF_HOME=/data/model-cache HF_HUB_DISABLE_TELEMETRY=1 PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "app.asgi:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--no-proxy-headers"]

FROM base AS web
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir -r requirements.lock
USER service

FROM base AS worker
ARG INSTALL_NLP=true
ARG NLP_PROFILE=cpu
# Optional CA secret is needed only in environments with a session HTTPS proxy.
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    if [ "$INSTALL_NLP" = true ]; then \
      if [ "$NLP_PROFILE" = cpu ]; then pip install --no-cache-dir -r requirements-cpu.lock; \
      elif [ "$NLP_PROFILE" = gpu ]; then pip install --no-cache-dir -r requirements-nlp.lock; \
      else echo 'NLP_PROFILE must be cpu or gpu' >&2; exit 1; fi; \
    else pip install --no-cache-dir -r requirements.lock; fi
USER service
CMD ["python", "-m", "app.worker"]
