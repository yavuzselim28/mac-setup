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

## Phase 1 — Fundament (Namespaces, Quotas, RBAC, LimitRange, NetworkPolicy)

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
sonst werden sie von der Quota abgelehnt — deshalb gibt es LimitRange (siehe 1.4)!

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
kubectl get resourcequota -A
```

### 1.4 LimitRange

LimitRange setzt Standardwerte für CPU/RAM wenn ein Pod keine Requests/Limits definiert.

**Warum wichtig?**  
Ohne LimitRange kann ein Tenant einen Pod ohne Resource Requests starten — dann greift die Quota nicht und der Pod kann unbegrenzt Ressourcen fressen. LimitRange ist die Absicherung der ResourceQuota.

**Zusammenspiel ResourceQuota + LimitRange:**
- **ResourceQuota** → Gesamtbudget des Namespace (z.B. max 4 CPU total)
- **LimitRange** → Standardwerte pro Container (z.B. default 100m CPU)

```yaml
# ~/limitrange.yaml
apiVersion: v1
kind: LimitRange
metadata:
  name: tenant-limits
  namespace: phoenix-dev
spec:
  limits:
    - type: Container
      default:            # Standard Limits wenn nichts angegeben
        cpu: 200m
        memory: 256Mi
      defaultRequest:     # Standard Requests wenn nichts angegeben
        cpu: 100m
        memory: 128Mi
      max:                # Maximale Werte pro Container
        cpu: "2"
        memory: 2Gi
      min:                # Minimale Werte pro Container
        cpu: 50m
        memory: 64Mi
---
apiVersion: v1
kind: LimitRange
metadata:
  name: tenant-limits
  namespace: atlas-dev
spec:
  limits:
    - type: Container
      default:
        cpu: 200m
        memory: 256Mi
      defaultRequest:
        cpu: 100m
        memory: 128Mi
      max:
        cpu: "1"
        memory: 1Gi
      min:
        cpu: 50m
        memory: 64Mi
```

```bash
kubectl apply -f ~/limitrange.yaml
kubectl get limitrange -A
```

### 1.5 RBAC (Role Based Access Control)

RBAC steuert wer was im Cluster darf.

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

### 1.6 NetworkPolicies (Tenant Isolation)

Standardmäßig kann jeder Pod mit jedem Pod im Cluster kommunizieren.  
NetworkPolicies sind Firewalls zwischen Namespaces — Tenant A kann nicht auf Tenant B zugreifen.

```yaml
# ~/networkpolicy.yaml — Phoenix Isolation
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: tenant-isolation
  namespace: phoenix-dev
spec:
  podSelector: {}         # gilt für alle Pods in diesem Namespace
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              tenant: phoenix
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              tenant: phoenix
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system   # DNS muss funktionieren
```

```yaml
# ~/networkpolicy-atlas.yaml — Atlas Isolation
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: tenant-isolation
  namespace: atlas-dev
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              tenant: atlas
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              tenant: atlas
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
```

```bash
kubectl apply -f ~/networkpolicy.yaml
kubectl apply -f ~/networkpolicy-atlas.yaml
kubectl get networkpolicy -A
```

**Ergebnis:**
- Phoenix Pods können nur mit Phoenix Pods reden
- Atlas Pods können nur mit Atlas Pods reden
- Kein Tenant kann den anderen sehen
- DNS funktioniert weiterhin für beide

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

OpenCost misst die Kosten pro Namespace/Tenant.  
Lokal: simulierte Preise. Auf ROSA: echte AWS Kosten.

**Verbindung zum PSF Modell:**
- ResourceQuota = gebuchte Kapazität (Nenner im PSF)
- OpenCost = tatsächlicher Verbrauch (Zähler im PSF)

```bash
helm repo add opencost https://opencost.github.io/opencost-helm-chart
helm repo update

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

**Traffic Kette:**
```
Browser → grafana.local
  → /etc/hosts → 127.0.0.1
    → NGINX Ingress (172.18.0.5)
      → Service monitoring-grafana
        → Pod 10.244.0.8:3000
```

```bash
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo update
helm install ingress-nginx ingress-nginx/ingress-nginx -n ingress-nginx --create-namespace

# /etc/hosts anpassen
sudo sh -c 'echo "127.0.0.1 grafana.local opencost.local ollama.local" >> /etc/hosts'

# Ingress Ressourcen anwenden
kubectl apply -f ~/ingress.yaml
kubectl get ingress -A
```

---

## Ollama + Open WebUI (Helm Chart)

```bash
ollama-start   # Pods starten → http://ollama.local
ollama-stop    # Pods stoppen + RAM freigeben
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
