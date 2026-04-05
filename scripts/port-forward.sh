#!/bin/bash
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# Loopback Alias setzen (wird nach Docker-Restart zurückgesetzt)
sudo ifconfig lo0 alias 10.254.254.254 255.255.255.255 2>/dev/null

# Warten bis K8s und Pod bereit
echo "[$(date)] ⏳ Warte auf Open WebUI Pod..."
for i in $(seq 1 30); do
    if kubectl get pods -n ollama 2>/dev/null | grep "open-webui" | grep "Running" &>/dev/null; then
        echo "[$(date)] ✅ Pod bereit"
        break
    fi
    sleep 5
done

# Port-Forward mit Auto-Restart
while true; do
    # Loopback Alias bei jedem Restart neu setzen
    sudo ifconfig lo0 alias 10.254.254.254 255.255.255.255 2>/dev/null
    echo "[$(date)] 🔄 Port-Forward starten..."
    kubectl port-forward svc/ollama-app-open-webui 3000:8080 -n ollama
    echo "[$(date)] ⚠️ Port-Forward gestorben — starte neu in 5s..."
    sleep 5
done
