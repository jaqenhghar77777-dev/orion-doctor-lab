set -euo pipefail
opts=(--init --hostname orion-replay --network=none --cap-drop=ALL --security-opt=no-new-privileges
  --read-only --pids-limit=512 --tmpfs /tmp:rw,exec,nosuid,nodev,mode=1777,size=2g
  --tmpfs /home/replay:rw,nosuid,nodev,mode=0700,uid=10001,gid=10001,size=2g)
case "$1" in
  migrations)
    status=0
    for variant in baseline upstream; do
      for mode in control missing; do
        echo "::group::$variant / $mode"
        log="$RUNNER_TEMP/pr-$variant-$mode.log"
        expected=migrated-to-38
        entry=(--entrypoint /bin/bash "orion-doctor-lab:$variant" /opt/lab/run.sh "$mode")
        if [[ "$variant/$mode" == baseline/missing ]]; then expected=maintenance-refusal-reached-doctor; fi
        if [[ "$variant/$mode" == upstream/missing ]]; then entry=(--entrypoint /bin/bash orion-doctor-lab:upstream /opt/pr-lab/repeat.sh); fi
        docker run --rm "${opts[@]}" "${entry[@]}" 2>&1 | tee "$log" || status=1
        result="$(sed -n 's/^RESULT //p' "$log")"
        if [[ -z "$result" ]]; then status=1
        else
          jq -r --arg label "$variant/$mode" '"* "+$label+" — Doctor exit "+(.doctorExit|tostring)+", agent schema "+(.before|tostring)+" → "+(.after|tostring)+", quick_check "+.integrity' <<<"$result" >> "$GITHUB_STEP_SUMMARY"
          jq -e --arg expect "$expected" '.observedPidCondition and .entered and .before==25 and .integrity=="ok" and .outcome==$expect and (if $expect=="migrated-to-38" then .doctorExit==0 and .after==38 else .doctorExit==1 and .after==25 end)' <<<"$result" >/dev/null || status=1
        fi
        if [[ "$variant/$mode" == upstream/missing ]]; then
          grep -q '^REPEAT doctorExit=0 synthetic-identity=preserved$' "$log" || status=1
          grep -E '^(REPEAT|DATABASES) ' "$log" >> "$GITHUB_STEP_SUMMARY" || status=1
        fi
        echo "::endgroup::"
      done
    done
    exit "$status"
    ;;
  probes)
    for mode in visible missing link-denied directory-missing boot-denied; do
      docker run --rm "${opts[@]}" --entrypoint node orion-doctor-lab:upstream /opt/pr-lab/probes.mjs "$mode"
    done
    ;;
  isolation)
    peer="$(docker run -d "${opts[@]}" --entrypoint node orion-doctor-lab:upstream /opt/pr-lab/probes.mjs peer)"
    trap 'docker rm -f "$peer" >/dev/null' EXIT
    data=''
    for _ in $(seq 1 30); do
      data="$(docker logs "$peer" | sed -n 's/^PEER //p')"
      if [[ -n "$data" ]]; then break; fi
      sleep 1
    done
    test -n "$data" && test "$(docker inspect -f '{{.State.Running}}' "$peer")" = true || exit 2
    log="$RUNNER_TEMP/pr-isolation.log"
    rc=0
    docker run --rm "${opts[@]}" --entrypoint node orion-doctor-lab:upstream /opt/pr-lab/probes.mjs compare "$data" | tee "$log" || rc=$?
    grep '^ISOLATION ' "$log" >> "$GITHUB_STEP_SUMMARY"
    if [[ "$rc" == 3 ]]; then echo "::error::Two verified distinct PID namespaces with hidden PID links were classified as the same."; fi
    exit "$rc"
    ;;
  *) exit 2 ;;
esac
