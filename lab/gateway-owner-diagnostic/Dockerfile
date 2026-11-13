FROM node:24.19.0-bookworm-slim
SHELL ["/bin/bash", "-euo", "pipefail", "-c"]
RUN test "$(uname -m)" = aarch64 && apt-get update && apt-get install -y --no-install-recommends git python3 make g++ ca-certificates && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /opt/beta /opt/lab && cd /tmp && npm pack --ignore-scripts --silent openclaw@2026.11.5-beta.1 && echo 'cc6d3b105b938acaf9301f17daa3985acd29fce0  openclaw-2026.11.5-beta.1.tgz' | sha1sum -c - && npm install --prefix /opt/beta --omit=dev --no-audit --no-fund /tmp/openclaw-2026.11.5-beta.1.tgz && rm /tmp/openclaw-2026.11.5-beta.1.tgz
COPY instrument.cjs mock.mjs handoff-fixture.mjs verify.py run.py /opt/lab/
RUN node /opt/lab/instrument.cjs
USER node
ENV HOME=/home/replay
WORKDIR /home/replay
ENTRYPOINT ["python3","/opt/lab/run.py"]
