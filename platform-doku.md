# Lokale Kubernetes Platform — Dokumentation

> Gebaut auf Docker Desktop (Kubernetes) auf einem MacBook Pro M5 Pro (64GB RAM)  
> Ziel: Multi-Tenant Platform lokal nachbauen — analog zu ROSA auf der Arbeit

---

## Architektur Überblick

```
Cluster (docker-desktop)
├── phoenix-dev      → Tenant "Phoenix" (Entwicklungsumgebung)
├── phoenix-prod     → Tenant "Phoenix" (Produktionsumgebung)
├── atlas-dev        → Tenant "Atlas" (Entwicklungsumgebung)
├── atlas-prod       → Tenant "Atlas" (Produktionsumgebung)
├── monitoring       → Prometheus + Grafana + OpenCost
├── ingress-nginx    → NGINX Ingress Controller
└── ollama           → Lokales LLM (Ollama + Open WebUI)
```

**Erreichbare Services (keine Port-Angabe nötig):**
- http://grafana.local → Grafana Dashboard
- http://opencost.local → OpenCost Chargeback
- http://ollama.local → Open WebUI (Ollama)

---

## ⚠️ Wichtig: Cluster Kontext

Dieser Stack läuft auf **docker-desktop**. Wenn du auch CRC (OpenShift Local) nutzt, stelle sicher dass der richtige Kontext aktiv ist:

```bash
kubectl config current-context   # sollte "docker-desktop" zeigen

# Falls CRC aktiv ist, zurück zu docker-desktop:
export KUBECONFIG=~/.kube/config
```

**NIEMALS** `export KUBECONFIG=~/.crc/machines/crc/kubeconfig` in `~/.zshrc` eintragen — das bricht docker-desktop Befehle!

Für CRC nur temporär setzen:
```bash
export KUBECONFIG=~/.crc/machines/crc/kubeconfig   # nur für diese Terminal Session
```

---

## Phase 1 — Fundament (Namespaces, Quotas, RBAC, LimitRange, NetworkPolicy)

### 1.1 Namespaces erstellen

```bash
kubectl create namespace phoenix-dev
kubectl create namespace phoenix-prod
kubectl create namespace atlas-dev
kubectl create namespace atlas-prod
```

### 1.2 Labels setzen

Labels verbinden alle Namespaces eines Tenants.  
OpenCost nutzt diese Labels um Kosten pro Tenant zu aggregieren.

```bash
kubectl label namespace phoenix-dev tenant=phoenix
kubectl label namespace phoenix-prod tenant=phoenix
kubectl label namespace atlas-dev tenant=atlas
kubectl label namespace atlas-prod tenant=atlas

kubectl get namespaces --show-labels
```

### 1.3 ResourceQuotas

Begrenzen wie viel CPU, RAM und Pods ein Tenant verbrauchen darf.  
Quota = gebuchte Kapazität im PSF Modell.

```bash
kubectl apply -f ~/quotas.yaml
kubectl get resourcequota -A
```

### 1.4 LimitRange

Setzt Standardwerte für CPU/RAM wenn ein Pod keine Requests/Limits definiert.  
Ohne LimitRange kann ein Pod die Quota umgehen!

```bash
kubectl apply -f ~/limitrange.yaml
kubectl get limitrange -A
```

### 1.5 RBAC

Steuert wer was im Cluster darf.

```bash
kubectl apply -f ~/rbac.yaml
kubectl get roles,rolebindings -A
```

### 1.6 NetworkPolicies

Firewall zwischen Namespaces — Tenant A kann nicht auf Tenant B zugreifen.

```bash
kubectl apply -f ~/networkpolicy.yaml
kubectl apply -f ~/networkpolicy-atlas.yaml
kubectl get networkpolicy -A
```

---

## Phase 2 — Monitoring (Prometheus + Grafana)

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
kubectl create namespace monitoring
helm install monitoring prometheus-community/kube-prometheus-stack -n monitoring
kubectl get pods -n monitoring
```

### Grafana öffnen

```bash
grafana-password   # Passwort holen
# Browser: http://grafana.local
# Login: admin / <passwort>
```

**Dashboard:** Dashboards → Kubernetes / Compute Resources / Namespace

---

## Phase 3 — Chargeback (OpenCost)

```bash
helm repo add opencost https://opencost.github.io/opencost-helm-chart
helm repo update

helm install opencost opencost/opencost -n monitoring \
  --set opencost.exporter.defaultClusterId=local \
  --set opencost.prometheus.internal.enabled=true \
  --set opencost.prometheus.internal.serviceName=monitoring-kube-prometheus-prometheus \
  --set opencost.prometheus.internal.namespaceName=monitoring \
  --set opencost.prometheus.internal.port=9090
```

**Browser:** http://opencost.local

---

## Phase 4 — Ingress (NGINX)

```bash
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo update
helm install ingress-nginx ingress-nginx/ingress-nginx -n ingress-nginx --create-namespace

# /etc/hosts einmalig anpassen
sudo sh -c 'echo "127.0.0.1 grafana.local opencost.local ollama.local" >> /etc/hosts'

# Ingress Ressourcen anwenden
kubectl apply -f ~/ingress.yaml
kubectl get ingress -A
```

### ⚠️ Bekanntes Problem: Ingress nach Docker Desktop Neustart

Nach jedem Docker Desktop Neustart:
- Die External-IP des Ingress Controllers kann sich ändern (intern, nicht erreichbar)
- Das `ollama-start` Script löst das automatisch mit `sudo kubectl port-forward` auf Port 80
- Beim ersten Start wird einmalig das sudo Passwort abgefragt

---

## Ollama + Open WebUI (Helm Chart)

```bash
ollama-start   # Pods starten + Port-Forward auf Port 80
ollama-stop    # Pods stoppen + RAM freigeben
```

### Modell pullen

```bash
# Im zweiten Terminal
kubectl port-forward svc/ollama-ollama 11434:11434 -n ollama &
curl http://localhost:11434/api/pull -d '{"model": "llama3.1:8b"}'
```

### Modell löschen

```bash
curl -X DELETE http://localhost:11434/api/delete -d '{"model": "modellname"}'
```

### Empfohlene Modelle für M5 Pro 64GB

| Modell | Größe | Empfehlung |
|--------|-------|------------|
| llama3.2:3b | ~2GB | Schnell, gut für Tests |
| llama3.1:8b | ~5GB | Beste Balance ✅ |
| mistral:7b | ~4GB | Sehr gut für Code |
| mixtral:8x7b | ~26GB | Stärkstes was komfortabel läuft |
| llama3.3:70b | ~43GB | Zu groß mit laufendem Stack |

---

## Start/Stop Scripts

### ~/ollama-k8s/start.sh

```bash
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

# Port-Forward auf Port 80 (sudo nötig für privilegierten Port)
sudo kubectl port-forward svc/ingress-nginx-controller 80:80 -n ingress-nginx &

echo "✅ Done!"
echo "🤖 Open WebUI: http://ollama.local"
echo "🔗 Grafana: http://grafana.local"
echo "🔗 OpenCost: http://opencost.local"
echo ""
echo "Press Ctrl+C to stop"
wait
```

### ~/ollama-k8s/stop.sh

```bash
#!/bin/bash
echo "🛑 Stopping Ollama + Open WebUI..."
pkill -f "port-forward svc/ollama-ollama" 2>/dev/null
pkill -f "port-forward svc/ollama-open-webui" 2>/dev/null
kubectl scale deployment ollama-ollama -n ollama --replicas=0
kubectl scale deployment ollama-open-webui -n ollama --replicas=0
echo "✅ Done! RAM freigegeben."
```

---

## Aliases (~/.zshrc)

```bash
alias ollama-start="~/ollama-k8s/start.sh"
alias ollama-stop="~/ollama-k8s/stop.sh"
alias grafana-pass="kubectl --namespace monitoring get secrets monitoring-grafana -o jsonpath=\"{.data.admin-password}\" | base64 -d ; echo"
alias grafana-password="kubectl --namespace monitoring get secrets monitoring-grafana -o jsonpath=\"{.data.admin-password}\" | base64 -d ; echo"
alias monitoring-start="kubectl scale deployment monitoring-grafana monitoring-kube-state-metrics opencost -n monitoring --replicas=1 && kubectl scale statefulset prometheus-monitoring-kube-prometheus-prometheus alertmanager-monitoring-kube-prometheus-alertmanager -n monitoring --replicas=1"
alias monitoring-stop="kubectl scale deployment monitoring-grafana monitoring-kube-state-metrics opencost -n monitoring --replicas=0 && kubectl scale statefulset prometheus-monitoring-kube-prometheus-prometheus alertmanager-monitoring-kube-prometheus-alertmanager -n monitoring --replicas=0"
```

---

## Nützliche Befehle

```bash
# Cluster Überblick
kubectl get nodes
kubectl get namespaces --show-labels
kubectl get pods -A

# Quota Verbrauch
kubectl get resourcequota -A

# LimitRange
kubectl get limitrange -A

# Roles und Bindings
kubectl get roles,rolebindings -A

# NetworkPolicies
kubectl get networkpolicy -A

# Ingress
kubectl get ingress -A
kubectl get svc -n ingress-nginx

# Logs
kubectl logs <pod-name> -n <namespace>

# Pod Details
kubectl describe pod <pod-name> -n <namespace>

# Deployment neu starten
kubectl rollout restart deployment/<name> -n <namespace>

# Interaktive Cluster UI
k9s

# Grafana Passwort
grafana-password

# Monitoring starten/stoppen
monitoring-start
monitoring-stop
```

---

## Helm Charts Übersicht

```bash
helm list -A
```

| Name | Namespace | Chart | Beschreibung |
|------|-----------|-------|--------------|
| ollama | ollama | ollama-chart | Ollama + Open WebUI |
| monitoring | monitoring | kube-prometheus-stack | Prometheus + Grafana |
| opencost | monitoring | opencost | Chargeback Tool |
| ingress-nginx | ingress-nginx | ingress-nginx | NGINX Ingress Controller |

---

## Zusammenhang mit der Arbeit (ROSA)

| Lokal | ROSA/Arbeit |
|-------|-------------|
| docker-desktop Cluster | ROSA Cluster auf AWS |
| Namespace phoenix-dev | Namespace kunde-a-dev |
| ResourceQuota | ResourceQuota |
| LimitRange | LimitRange |
| RBAC | RBAC + OpenShift Groups |
| NetworkPolicy | NetworkPolicy |
| Prometheus | Eigene Prometheus Instanz |
| OpenCost lokal | OpenCost auf ROSA |
| Simulierte Kosten | Echte AWS Kosten |
| NGINX Ingress | HAProxy / OpenShift Router |
| grafana.local | grafana.firma.de |
