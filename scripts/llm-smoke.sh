#!/bin/sh
# Smoke test of the LLM in the cluster (D23). From a pod with the worker's
# identity, the only one the NetworkPolicies let through, it classifies
# three unambiguous posts with the same JSON-schema output the worker will
# use, and checks the labels. Prints a PASS/FAIL table with latencies; exits
# 1 on any FAIL. Sarcasm is left out on purpose: it is a known weak spot
# (D22), measured by tools/llm_eval.py, not a smoke test.
#
# Inputs (environment, set by the Makefile): KUBE_CONTEXT, CURL_IMAGE
# POSIX sh on purpose: it must run with both Linux and macOS userland.

set -eu

: "${KUBE_CONTEXT:?}" "${CURL_IMAGE:?}"
kubectl="kubectl --context $KUBE_CONTEXT"

NS=analysis
POD=llm-smoke
URL=http://llm.analysis.svc:8080
SYSTEM="You classify the sentiment of one social media post. \
positive: approval, joy, praise, gratitude, excitement. \
negative: complaints, anger, sadness, criticism, including sarcasm that criticises. \
neutral: facts, news, questions or announcements without a clear feeling. \
The post may be in any language. Answer with JSON only."
# OpenAI's response_format shape; llama-server v0.5.0 ignores the one its
# README documents (D22).
FORMAT='{"type":"json_schema","json_schema":{"name":"sentiment","strict":true,"schema":{"type":"object","properties":{"label":{"type":"string","enum":["positive","neutral","negative"]}},"required":["label"],"additionalProperties":false}}}'

trap '$kubectl delete pod "$POD" -n "$NS" --ignore-not-found --wait=false >/dev/null 2>&1 || true' EXIT
trap 'exit 130' INT TERM
$kubectl delete pod "$POD" -n "$NS" --ignore-not-found --wait=true >/dev/null 2>&1 || true

echo "Starting a test pod with the worker's identity..."
$kubectl run "$POD" -n "$NS" --image="$CURL_IMAGE" --image-pull-policy=Never --restart=Never \
  --labels="app.kubernetes.io/component=worker,socialsignal/test=llm-smoke" \
  --command -- sleep 600 >/dev/null
$kubectl wait --for=condition=Ready "pod/$POD" -n "$NS" --timeout=120s >/dev/null
# k3s applies policies to a new pod a few hundred ms after it starts (#14711).
sleep 5

health=$($kubectl exec "$POD" -n "$NS" -- \
  curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$URL/health") || health=000
if [ "$health" != 200 ]; then
  echo "The LLM is not ready: /health answered $health." >&2
  exit 1
fi

failures=0
check() { # expected text
  body=$(printf '{"temperature":0,"max_tokens":16,"messages":[{"role":"system","content":"%s"},{"role":"user","content":"%s"}],"response_format":%s}' \
    "$SYSTEM" "$2" "$FORMAT")
  # The body goes through stdin. The reply is the JSON, then the time on
  # its own line.
  reply=$(printf '%s' "$body" | $kubectl exec -i "$POD" -n "$NS" -- \
    curl -s --max-time 120 -H 'Content-Type: application/json' -d @- \
    -w '\n%{time_total}' "$URL/v1/chat/completions") || reply=""
  seconds=$(printf '%s\n' "$reply" | tail -n 1)
  # The label sits in the escaped JSON of message.content: ...label\": \"positive...
  got=$(printf '%s' "$reply" | grep -o 'label[^a-z]*[a-z]*' | head -n 1 | sed 's/.*[^a-z]//')
  if [ "$got" = "$1" ]; then
    result=PASS
  else
    result=FAIL
    failures=$((failures + 1))
  fi
  printf '%-5s %6.1fs  expected %-8s got %-8s %s\n' "$result" "${seconds:-0}" "$1" "${got:-none}" "$2"
}

echo
check positive "What a wonderful day, I love this community!"
check negative "This app crashes every time I open it. Worst update ever."
check neutral "The meeting starts at 10 am in room 4."

echo
if [ "$failures" -eq 0 ]; then
  echo "LLM smoke test passed: 3/3."
else
  echo "LLM smoke test FAILED: $failures of 3." >&2
  exit 1
fi
