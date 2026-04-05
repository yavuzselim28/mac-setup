#!/bin/bash
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# Port-Forward mit Auto-Restart
while true; do
    kubectl port-forward svc/ollama-app-open-webui 3000:8080 -n ollama
    echo "[$(date)] Port-Forward gestorben — starte neu in 5s..."
    sleep 5
done
