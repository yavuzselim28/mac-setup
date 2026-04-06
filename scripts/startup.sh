#!/bin/bash
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

LOG="$HOME/mac-setup/agent/startup.log"
echo "[$(date)] 🚀 Startup Script gestartet" >> $LOG

# Warten bis Docker bereit
echo "[$(date)] ⏳ Warte auf Docker..." >> $LOG
for i in $(seq 1 30); do
    if docker ps &>/dev/null; then
        echo "[$(date)] ✅ Docker bereit" >> $LOG
        break
    fi
    sleep 5
done

# Warten bis K8s bereit
echo "[$(date)] ⏳ Warte auf K8s..." >> $LOG
for i in $(seq 1 20); do
    if kubectl get pods -n ollama &>/dev/null; then
        echo "[$(date)] ✅ K8s bereit" >> $LOG
        break
    fi
    sleep 5
done

# Crash-Counter zurücksetzen
python3 -c "
import json
from pathlib import Path
f = Path.home() / 'mac-setup/agent/agent_state.json'
d = json.loads(f.read_text()) if f.exists() else {}
d['llama_restarts'] = []
f.write_text(json.dumps(d))
" >> $LOG 2>&1
echo "[$(date)] ✅ Crash-Counter zurückgesetzt" >> $LOG

# Loopback Alias
sudo ifconfig lo0 alias 10.254.254.254 255.255.255.255 >> $LOG 2>&1
echo "[$(date)] ✅ Loopback Alias gesetzt" >> $LOG

# GPU Memory Limit
sudo sysctl iogpu.wired_limit_mb=52429 >> $LOG 2>&1
echo "[$(date)] ✅ GPU Limit gesetzt" >> $LOG

# K8s Pods hochfahren
kubectl scale deployment ollama-app-ollama -n ollama --replicas=1 >> $LOG 2>&1
kubectl scale deployment ollama-app-open-webui -n ollama --replicas=1 >> $LOG 2>&1
echo "[$(date)] ✅ K8s Pods gestartet" >> $LOG

# llama-server starten mit nohup — überlebt LaunchAgent Ende
echo "[$(date)] 🧠 Starte llama-server..." >> $LOG
lsof -ti:8080 | xargs kill -9 2>/dev/null
lsof -ti:8082 | xargs kill -9 2>/dev/null
sleep 2

nohup /Users/yavuztopcu/llama-cpp-turboquant/build/bin/llama-server \
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
  --draft-min 2 >> $LOG 2>&1 &

disown $!
echo "[$(date)] ✅ llama-server gestartet (PID $!)" >> $LOG
