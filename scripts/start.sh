#!/bin/bash
sudo sysctl iogpu.wired_limit_mb=52429 2>/dev/null
echo "🚀 Starting Platform Stack..."

# Loopback Alias für AI Backend
sudo ifconfig lo0 alias 10.254.254.254 255.255.255.255 2>/dev/null

# Ollama für kagent starten (falls nicht bereits läuft)
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
  echo "🤖 Starte Ollama (kagent LLM Backend)..."
  OLLAMA_CONTEXT_LENGTH=65536 ollama serve &
  sleep 5
  echo "✅ Ollama läuft auf Port 11434"
else
  echo "✅ Ollama läuft bereits"
fi

# K8s Pods hochfahren
kubectl scale deployment ollama-app-ollama -n phoenix --replicas=1
kubectl scale deployment ollama-app-open-webui -n phoenix --replicas=1
echo "⏳ Warte bis Pods ready sind..."
kubectl wait --for=condition=ready pod -l app=ollama-app-ollama -n phoenix --timeout=120s
kubectl wait --for=condition=ready pod -l app=ollama-app-open-webui -n phoenix --timeout=120s

# Ingress Port-Forward killen falls noch aktiv
sudo pkill -f "port-forward svc/ingress-nginx" 2>/dev/null
sleep 2

# Port-Forward auf Port 80 (ollama.local)
sudo kubectl port-forward svc/ingress-nginx-controller 80:80 -n ingress-nginx &

echo "✅ Done!"
echo "🤖 Open WebUI: http://ollama.local"
echo "🔗 Grafana:    http://grafana.local"
echo "🔗 OpenCost:   http://opencost.local"
echo "🤖 kagent LLM: http://localhost:11434"
echo ""
echo "AI Backends starten:"
echo "  ai-qwen-vllm   → vllm-swift + TurboQuant (Port 8083) ✅ empfohlen"
echo "  ai-qwen-mlx    → ekryski MLXServer (Port 8081)"
echo "  ai-gemma-mlx   → SwiftLM Gemma (Port 8081)"
echo ""
echo "Press Ctrl+C to stop"
wait
