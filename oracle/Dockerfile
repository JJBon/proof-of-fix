# The oracle node's image (proof-of-fix#94). Standard library only, so the base image is all it needs.
# Pinned by digest: Python 3.12 on Alpine, the same image the loop tests fixes with (scripts/bounty-loop.sh).
# Build from the repository root:  docker build -f oracle/Dockerfile -t pof-oracle-node .
# The image's own digest is what a node reports as `checker_image` (POF_ORACLE_IMAGE) and what a dstack attestation
# measures; publish the digest with each release so anyone can check a node runs it.
# No Docker CLI (#116): given the host's Docker socket, the node starts each fix's tests in a sibling container through
# the Docker Engine API (oracle/sandbox.py DockerApi, standard library). See validator-kit/terraform/node-user-data.sh.tftpl.
FROM python@sha256:e6dae589c1c05976188fd3bd019afd091445fc533ed2ea29001beddc7368a9c8

# git: the node fetches each claimed commit itself (oracle/fetch.py, #115). The image's digest pins what's in it.
RUN apk add --no-cache git && adduser -D -u 10001 oracle
WORKDIR /app
COPY oracle/ /app/oracle/
# The judge's prompt, verdict parser and fake (pof/judges, #89) and the gateway client (scripts/judge_run.py).
COPY pof/ /app/pof/
# The v2 node finds a submission's pull request through the bot's repository host adapters (bot/forge.py, #104).
COPY bot/ /app/bot/
COPY scripts/judge_run.py /app/scripts/judge_run.py
USER oracle
ENV PYTHONDONTWRITEBYTECODE=1
ENTRYPOINT ["python3", "-m", "oracle"]
CMD ["info"]
