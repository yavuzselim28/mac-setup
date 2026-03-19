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

**Erreichbare Services (keine Port-Forwards nötig!):**
- http://grafana.local → Grafana Dashboard
- http://opencost.local → OpenCost Chargeback
- http://ollama.local → Open WebUI (Ollama)

---

## Phase 1 — Fundament (Namespaces, Quotas, RBAC)

### 1.1 Namespaces erstellen

Ein Namespace ist eine logische Isolationsschicht im Cluster.  
Jeder Tenant bekommt eigene Namespaces — dev und prod getrennt.

```bash
kubectl create namespace phoenix-dev
kubectl create namespace phoenix-prod
kubectl create namespace atlas-dev
kubectl create namespace atlas-prod
```

### 1.2 Labels setzen

Labels verbinden alle Namespaces eines Tenants.  
OpenCost nutzt diese Labels später um Kosten pro Tenant zu aggregieren.

```bash
kubectl label namespace phoenix-dev tenant=phoenix
kubectl label namespace phoenix-prod tenant=phoenix
kubectl label namespace atlas-dev tenant=atlas
kubectl label namespace atlas-prod tenant=atlas
```

Verifizieren:
```bash
kubectl get namespaces --show-labels
```

### 1.3 ResourceQuotas

ResourceQuotas begrenzen wie viel CPU, RAM und Pods ein Tenant verbrauchen darf.  
Das ist der technische Unterbau des Chargeback Modells — Quota = gebuchte Kapazität.

**Wichtig:** Pods müssen `resources.requests` und `resources.limits` gesetzt haben,  
sonst werden sie von der Quota abgelehnt!

```yaml
# ~/quotas.yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: phoenix-quota
  namespace: phoenix-dev
spec:
  hard:
    requests.cpu: "2"       # Minimum reserviert
    requests.memory: 4Gi   # Minimum reserviert
    limits.cpu: "4"         # Maximum erlaubt
    limits.memory: 8Gi     # Maximum erlaubt
    pods: "10"              # Maximale Pod-Anzahl
---
apiVersion: v1
kind: ResourceQuota
metadata:
  name: phoenix-quota
  namespace: phoenix-prod
spec:
  hard:
    requests.cpu: "4"
    requests.memory: 8Gi
    limits.cpu: "8"
    limits.memory: 16Gi
    pods: "20"
---
apiVersion: v1
kind: ResourceQuota
metadata:
  name: atlas-quota
  namespace: atlas-dev
spec:
  hard:
    requests.cpu: "1"
    requests.memory: 2Gi
    limits.cpu: "2"
    limits.memory: 4Gi
    pods: "5"
---
apiVersion: v1
kind: ResourceQuota
metadata:
  name: atlas-quota
  namespace: atlas-prod
spec:
  hard:
    requests.cpu: "2"
    requests.memory: 4Gi
    limits.cpu: "4"
    limits.memory: 8Gi
    pods: "10"
```

```bash
kubectl apply -f ~/quotas.yaml
kubectl get resourcequota -A   # Verbrauch vs. Limit anzeigen
```

**Logik:**
- Phoenix ist ein größerer Kunde → mehr Quota
- Atlas ist ein kleinerer Kunde → weniger Quota
- Prod hat immer mehr Kapazität als Dev

### 1.4 RBAC (Role Based Access Control)

RBAC steuert wer was im Cluster darf.  
Jeder Tenant bekommt eine Role (Berechtigungen) und ein RoleBinding (wer bekommt diese Role).

**Konzept:**
- **Role** → definiert Berechtigungen (get, list, create, delete etc.)
- **RoleBinding** → verbindet einen User mit einer Role
- **Scope** → Roles gelten nur im jeweiligen Namespace

```yaml
# ~/rbac.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: tenant-role
  namespace: phoenix-dev
rules:
  - apiGroups: ["", "apps"]
    resources: ["pods", "deployments", "services", "configmaps"]
    verbs: ["get", "list", "watch", "create", "update", "delete"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: phoenix-binding
  namespace: phoenix-dev
subjects:
  - kind: User
    name: phoenix-user
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: tenant-role
  apiGroup: rbac.authorization.k8s.io
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: tenant-role
  namespace: atlas-dev
rules:
  - apiGroups: ["", "apps"]
    resources: ["pods", "deployments", "services", "configmaps"]
    verbs: ["get", "list", "watch", "create", "update", "delete"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: atlas-binding
  namespace: atlas-dev
subjects:
  - kind: User
    name: atlas-user
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: tenant-role
  apiGroup: rbac.authorization.k8s.io
```

```bash
kubectl apply -f ~/rbac.yaml
kubectl get roles,rolebindings -A
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
# Passwort holen
grafana-password   # (Alias, siehe unten)

# Browser: http://grafana.local
# Login: admin / <passwort>
```

**Dashboard:** Dashboards → Kubernetes / Compute Resources / Namespace

---

## Phase 3 — Chargeback (OpenCost)

OpenCost misst die Kosten pro Namespace/Tenant.  
Lokal: simulierte Preise (AWS us-east-1 Standard).  
Auf ROSA: echte AWS Kosten.

**Verbindung zum PSF Modell:**
- ResourceQuota = gebuchte Kapazität (Nenner im PSF)
- OpenCost = tatsächlicher Verbrauch (Zähler im PSF)

```bash
helm repo add opencost https://opencost.github.io/opencost-helm-chart
helm repo update

# OpenCost auf unseren Prometheus zeigen
helm install opencost opencost/opencost -n monitoring \
  --set opencost.exporter.defaultClusterId=local \
  --set opencost.prometheus.internal.enabled=true \
  --set opencost.prometheus.internal.serviceName=monitoring-kube-prometheus-prometheus \
  --set opencost.prometheus.internal.namespaceName=monitoring \
  --set opencost.prometheus.internal.port=9090

kubectl get pods -l app.kubernetes.io/instance=opencost -n monitoring
```

**Browser:** http://opencost.local

---

## Phase 4 — Ingress (NGINX)

Statt Port-Forwards sind alle Services über lokale URLs erreichbar.  
Der Ingress Controller empfängt HTTP Traffic und leitet ihn zum richtigen Service weiter.  
Auf ROSA übernimmt diese Rolle der OpenShift Router (HAProxy).

### NGINX Ingress Controller installieren

```bash
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo update
helm install ingress-nginx ingress-nginx/ingress-nginx -n ingress-nginx --create-namespace
```

### /etc/hosts anpassen

Damit dein Mac die lokalen URLs auflösen kann:

```bash
sudo sh -c 'echo "127.0.0.1 grafana.local opencost.local ollama.local" >> /etc/hosts'
```

### Ingress Ressourcen erstellen

```yaml
# ~/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: monitoring-ingress
  namespace: monitoring
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  ingressClassName: nginx
  rules:
    - host: grafana.local
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: monitoring-grafana
                port:
                  number: 80
    - host: opencost.local
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: opencost
                port:
                  number: 9090
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: ollama-ingress
  namespace: ollama
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  ingressClassName: nginx
  rules:
    - host: ollama.local
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: ollama-open-webui
                port:
                  number: 8080
```

```bash
kubectl apply -f ~/ingress.yaml
kubectl get ingress -A
```

---

## Ollama + Open WebUI (Helm Chart)

Ollama läuft als eigenes Helm Chart im `ollama` Namespace.  
Modelle werden auf einem PersistentVolume gespeichert — überleben Pod-Neustarts.

```bash
# Starten (Pods hochfahren)
ollama-start

# Stoppen (Pods herunterfahren + RAM freigeben)
ollama-stop

# Browser: http://ollama.local
```

### Modell pullen

```bash
curl http://localhost:11434/api/pull -d '{"model": "llama3.1:8b"}'
```

---

## Aliases (~/.zshrc)

```bash
alias ollama-start="~/ollama-k8s/start.sh"
alias ollama-stop="~/ollama-k8s/stop.sh"
alias grafana-pass="kubectl --namespace monitoring get secrets monitoring-grafana -o jsonpath=\"{.data.admin-password}\" | base64 -d ; echo"
alias grafana-password="kubectl --namespace monitoring get secrets monitoring-grafana -o jsonpath=\"{.data.admin-password}\" | base64 -d ; echo"
```

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
echo "✅ Done!"
echo "🤖 Open WebUI: http://ollama.local"
echo "🔗 Ollama API: http://localhost:11434"
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

## Nützliche Befehle

```bash
# Cluster Überblick
kubectl get nodes
kubectl get namespaces --show-labels
kubectl get pods -A

# Quota Verbrauch anzeigen
kubectl get resourcequota -A

# Alle Roles und Bindings
kubectl get roles,rolebindings -A

# Ingress anzeigen
kubectl get ingress -A

# Services anzeigen
kubectl get svc -n monitoring

# Logs eines Pods
kubectl logs <pod-name> -n <namespace>

# Pod Details
kubectl describe pod <pod-name> -n <namespace>

# Deployment neu starten
kubectl rollout restart deployment/<name> -n <namespace>

# Interaktive Cluster UI
k9s

# Grafana Passwort
grafana-password
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
| RBAC | RBAC + OpenShift Groups |
| Prometheus | Eigene Prometheus Instanz |
| OpenCost lokal | OpenCost auf ROSA |
| Simulierte Kosten | Echte AWS Kosten |
| NGINX Ingress | HAProxy / OpenShift Router |
| grafana.local | grafana.firma.de |
