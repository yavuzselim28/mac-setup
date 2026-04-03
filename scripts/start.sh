#!/bin/bash
echo "🚀 Starting Ollama + Open WebUI..."
kubectl scale deployment ollama-ollama -n ollama --replicas=1
kubectl scale deployment ollama-open-webui -n ollama --replicas=1
echo "⏳ Warte bis Pods ready sind..."
kubectl wait --for=condition=ready pod -l app=ollama-ollama -n ollama --timeout=120s
kubectl wait --for=condition=ready pod -l app=ollama-open-webui -n ollama --timeout=120s
sleep 10

# Alten Port-Forward killen falls noch aktiv
sudo pkill -f "port-forward svc/ingress-nginx" 2>/dev/null
sleep 2

# Port-Forward auf Port 80
sudo kubectl port-forward svc/ingress-nginx-controller 80:80 -n ingress-nginx &

# TurboQuant llama-server starten
echo "🧠 Starting TurboQuant llama-server (Llama 3.3 70B)..."
lsof -ti:8080 | xargs kill -9 2>/dev/null
sleep 1
cd ~/llama-cpp-turboquant && ./build/bin/llama-server \
  -m ~/models/llama33-70b-q4km.gguf \
  --cache-type-k turbo3 \
  --cache-type-v turbo3 \
  -ngl 99 \
  -c 32768 \
  -fa on \
  --host 0.0.0.0 --port 8080 &

echo "✅ Done!"
echo "🤖 Open WebUI: http://ollama.local"
echo "🔗 Grafana: http://grafana.local"
echo "🔗 OpenCost: http://opencost.local"
echo "🧠 TurboQuant: http://localhost:8080"
echo ""
echo "Press Ctrl+C to stop"
wait
