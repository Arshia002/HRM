FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1 PYTHONPATH=/app/src
RUN python -m pip install --no-cache-dir --disable-pip-version-check cryptography==50.0.1
COPY src /app/src
COPY web /app/web
COPY data/seed/sazmanhr-seed.sqlite /app/data/seed/sazmanhr-seed.sqlite
COPY deploy/linux-web-test/healthcheck.py /app/healthcheck.py
RUN useradd --system --uid 10001 hrm && mkdir -p /data && chown -R hrm:hrm /data /app
USER hrm
EXPOSE 8080
HEALTHCHECK --interval=20s --timeout=5s --retries=5 CMD ["python","/app/healthcheck.py"]
CMD ["python","-m","sazmanhr.server","--host","0.0.0.0","--port","8080","--data-dir","/data","--seed","/app/data/seed/sazmanhr-seed.sqlite","--tls-mode","off","--web-root","/app/web"]
