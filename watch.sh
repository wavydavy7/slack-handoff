#!/bin/bash
# Blocks until requests.jsonl has unprocessed lines, prints them, and exits.
# Claude runs this in the background; its exit is the "new request" signal.
BRIDGE="$(cd "$(dirname "$0")" && pwd)/bridge"
REQS="$BRIDGE/requests.jsonl"
DONE="$BRIDGE/processed_count"
mkdir -p "$BRIDGE"
touch "$REQS"
[ -f "$DONE" ] || echo 0 > "$DONE"
while true; do
  total=$(wc -l < "$REQS" | tr -d ' ')
  processed=$(cat "$DONE")
  if [ "$total" -gt "$processed" ]; then
    echo "NEW_REQUESTS (processed=$processed total=$total):"
    tail -n +"$((processed + 1))" "$REQS"
    exit 0
  fi
  sleep 1
done
