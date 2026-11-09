FROM orion-doctor-lab:baseline
USER root
COPY custody-host.mjs custody-worker.cjs patch.cjs safeguards.mjs check-worker.mjs /opt/lab/
RUN --network=none NODE_PATH=/opt/trace/node_modules node /opt/lab/patch.cjs
COPY compare.sh /opt/lab/
USER replay
ENTRYPOINT ["/bin/bash", "/opt/lab/compare.sh"]
