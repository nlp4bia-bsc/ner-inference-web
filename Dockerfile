FROM python:3.12-slim
WORKDIR /service
ARG INSTALL_NLP=false
COPY requirements.lock requirements-nlp.lock ./
# Optional CA secret is needed only in environments with a session HTTPS proxy.
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    if [ "$INSTALL_NLP" = true ]; then \
      pip install --no-cache-dir -r requirements-nlp.lock; \
    else pip install --no-cache-dir -r requirements.lock; fi
COPY app ./app
COPY scripts ./scripts
COPY catalog ./catalog
RUN useradd --uid 10001 --create-home service && mkdir /data && chown -R service:service /data /service
USER service
ENV STORAGE_ROOT=/data HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "app.asgi:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--no-proxy-headers"]
