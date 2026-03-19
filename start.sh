#!/bin/bash
echo "🚀 Starting Ollama + Open WebUI..."
kubectl scale deployment ollama-ollama -n ollama --replicas=1
kubectl scale deployment ollama-open-webui -n ollama --replicas=1
echo "⏳ Warte bis Pods ready sind..."
kubectl wait --for=condition=ready pod -l app=ollama-ollama -n ollama --timeout=120s
kubectl wait --for=condition=ready pod -l app=ollama-open-webui -n ollama --timeout=120s
sleep 10

# /etc/hosts auf 127.0.0.1 setzen falls nötig
CURRENT_IP=$(grep "grafana.local" /etc/hosts | awk '{print $1}')
if [ "$CURRENT_IP" != "127.0.0.1" ]; then
  echo "🌐 /etc/hosts wird auf 127.0.0.1 gesetzt..."
  sudo sed -i '' "s/.*grafana.local.*/127.0.0.1        grafana.local opencost.local ollama.local/" /etc/hosts
fi

# Port-Forward auf Port 80
sudo kubectl port-forward svc/ingress-nginx-controller 80:80 -n ingress-nginx &

echo "✅ Done!"
echo "🤖 Open WebUI: http://ollama.local"
echo "🔗 Grafana: http://grafana.local"
echo "🔗 OpenCost: http://opencost.local"
echo ""
echo "Press Ctrl+C to stop"
wait
