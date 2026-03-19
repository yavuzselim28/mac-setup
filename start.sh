#!/bin/bash
echo "🚀 Starting Ollama + Open WebUI..."
kubectl scale deployment ollama-ollama -n ollama --replicas=1
kubectl scale deployment ollama-open-webui -n ollama --replicas=1
echo "⏳ Warte bis Pods ready sind..."
kubectl wait --for=condition=ready pod -l app=ollama-ollama -n ollama --timeout=120s
kubectl wait --for=condition=ready pod -l app=ollama-open-webui -n ollama --timeout=120s
sleep 10

# Ingress IP automatisch erkennen
INGRESS_IP=$(kubectl get svc ingress-nginx-controller -n ingress-nginx -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
CURRENT_IP=$(grep "grafana.local" /etc/hosts | awk '{print $1}')

if [ -n "$INGRESS_IP" ] && [ "$INGRESS_IP" != "$CURRENT_IP" ]; then
  echo "🌐 IP hat sich geändert: $CURRENT_IP → $INGRESS_IP"
  sudo sed -i '' "s/.*grafana.local.*/$INGRESS_IP        grafana.local opencost.local ollama.local/" /etc/hosts
  echo "✅ /etc/hosts aktualisiert"
else
  echo "🌐 IP unverändert: $CURRENT_IP"
fi

echo "✅ Done!"
echo "🤖 Open WebUI: http://ollama.local"
echo "🔗 Grafana: http://grafana.local"
echo "🔗 OpenCost: http://opencost.local"
echo ""
echo "Press Ctrl+C to stop"
wait
