# The exchange service's image (proof-of-fix#117). Standard library only: the base image is all it needs.
# Pinned by digest: the oracle node's base (oracle/Dockerfile), Python 3.12 on Alpine.
# Build from the repository root:  docker build -f exchange/Dockerfile -t pof-exchange .
FROM python@sha256:e6dae589c1c05976188fd3bd019afd091445fc533ed2ea29001beddc7368a9c8

RUN adduser -D -u 10002 exchange && mkdir /state && chown exchange /state
WORKDIR /app
# The service checks signatures and reads the draw with the node's own code (oracle/v2.py, crypto, rpc).
COPY oracle/ /app/oracle/
COPY exchange/ /app/exchange/
USER exchange
ENV PYTHONDONTWRITEBYTECODE=1 EXCHANGE_HOST=0.0.0.0 EXCHANGE_PORT=8560 EXCHANGE_STATE=/state/exchange.jsonl
EXPOSE 8560
HEALTHCHECK --interval=30s --timeout=3s CMD python3 -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8560/healthz', timeout=2)" || exit 1
ENTRYPOINT ["python3", "-m", "exchange"]
