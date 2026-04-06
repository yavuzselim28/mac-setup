#!/bin/bash
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

# Warten bis K8s bereit
sleep 30

cd /Users/yavuztopcu/llama-cpp-turboquant

exec ./build/bin/llama-server \
  -m /Users/yavuztopcu/models/llama33-70b-q4km.gguf \
  --model-draft /Users/yavuztopcu/models/llama31-8b-draft.gguf \
  --cache-type-k turbo4 \
  --cache-type-v turbo4 \
  --cache-type-k-draft turbo4 \
  --cache-type-v-draft turbo4 \
  -ngl 99 \
  -c 16384 \
  -np 1 \
  -fa on \
  --host 0.0.0.0 --port 8080 \
  --draft-max 8 \
  --draft-min 2
