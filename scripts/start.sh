#!/bin/bash
sudo sysctl iogpu.wired_limit_mb=52429 2>/dev/null
echo "🚀 Starting Ollama + Open WebUI..."
kubectl scale deployment ollama-app-ollama -n ollama --replicas=1
kubectl scale deployment ollama-app-open-webui -n ollama --replicas=1
echo "⏳ Warte bis Pods ready sind..."
kubectl wait --for=condition=ready pod -l app=ollama-app-ollama -n ollama --timeout=120s
kubectl wait --for=condition=ready pod -l app=ollama-app-open-webui -n ollama --timeout=120s
sleep 10

# Alten Port-Forward killen falls noch aktiv
sudo pkill -f "port-forward svc/ingress-nginx" 2>/dev/null
sleep 2

# Port-Forward auf Port 80
sudo kubectl port-forward svc/ingress-nginx-controller 80:80 -n ingress-nginx &

echo "✅ Done!"
echo "🤖 Open WebUI: http://ollama.local"
echo "🔗 Grafana: http://grafana.local"
echo "🔗 OpenCost: http://opencost.local"
echo ""
echo "Starte jetzt in einem neuen Terminal: ai-llama / ai-qwen / ai-mistral"
echo ""
echo "Press Ctrl+C to stop"
wait
