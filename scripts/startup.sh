#!/bin/bash

LOG="$HOME/mac-setup/agent/startup.log"
echo "[$(date)] 🚀 Startup Script gestartet" >> $LOG

# Warten bis Docker hochgefahren ist
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

# GPU Memory Limit setzen
sudo sysctl iogpu.wired_limit_mb=52429 >> $LOG 2>&1
echo "[$(date)] ✅ GPU Limit gesetzt" >> $LOG

# K8s Pods hochfahren
kubectl scale deployment ollama-app-ollama -n ollama --replicas=1 >> $LOG 2>&1
kubectl scale deployment ollama-app-open-webui -n ollama --replicas=1 >> $LOG 2>&1
echo "[$(date)] ✅ K8s Pods gestartet" >> $LOG

# Port-Forward starten
sudo kubectl port-forward svc/ingress-nginx-controller 80:80 -n ingress-nginx >> $LOG 2>&1 &
echo "[$(date)] ✅ Port-Forward gestartet" >> $LOG

# Platform Agent ausführen
/opt/homebrew/bin/python3 $HOME/mac-setup/agent/platform_agent.py >> $LOG 2>&1
echo "[$(date)] ✅ Platform Agent initial run fertig" >> $LOG
