#!/bin/bash
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

sudo ifconfig lo0 alias 10.254.254.254 255.255.255.255 2>/dev/null

echo "[$(date)] ⏳ Warte auf Open WebUI Pod..."
for i in $(seq 1 30); do
    if kubectl get pods -n ollama 2>/dev/null | grep "open-webui" | grep "Running" &>/dev/null; then
        echo "[$(date)] ✅ Pod bereit"
        break
    fi
    sleep 5
done

while true; do
    sudo ifconfig lo0 alias 10.254.254.254 255.255.255.255 2>/dev/null
    echo "[$(date)] 🔄 Port-Forward starten..."
    kubectl port-forward --address 0.0.0.0 \
      -n ollama \
      deployment/ollama-app-open-webui \
      3000:8080
    echo "[$(date)] ⚠️ Port-Forward gestorben — starte neu in 5s..."
    sleep 5
done
