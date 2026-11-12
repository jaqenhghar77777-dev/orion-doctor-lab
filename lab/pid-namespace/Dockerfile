FROM orion-doctor-lab:baseline
USER root
COPY backport.cjs upstream.ts probes.mjs verify.mjs repeat.sh /opt/pr-lab/
RUN --network=none NODE_PATH=/opt/trace/node_modules node /opt/pr-lab/backport.cjs \
    /opt/pr-lab/upstream.ts /opt/beta/node_modules/openclaw/dist /opt/pr-lab/api.mjs 12
USER replay
