# OpenShift Local (CRC) — Setup Anleitung

> OpenShift Local läuft als eigene VM auf deinem Mac — komplett getrennt von Docker Desktop.
> Ziel: Lokales OpenShift zum Lernen und Testen, analog zu ROSA auf der Arbeit.

---

## Installation

### 1. CRC installieren

Download von: https://console.redhat.com/openshift/create/local
- macOS Apple Silicon Version herunterladen
- Pull Secret herunterladen (braucht kostenlosen Red Hat Account)
- Red Hat Account: https://developers.redhat.com/register

```bash
# Version prüfen
crc version
```

### 2. Setup ausführen

```bash
crc setup
# Telemetry Frage: n
```

Lädt ca. 6GB Bundle herunter — einmalig.

### 3. CRC starten

```bash
crc start --pull-secret-file ~/Downloads/pull-secret.txt
```

Beim ersten Start werden Login-Daten angezeigt — notieren!

```
Log in as administrator:
  Username: kubeadmin
  Password: <passwort>

Log in as user:
  Username: developer
  Password: developer
```

---

## Konfiguration

### PATH und KUBECONFIG setzen

```bash
# Einmalig in ~/.zshrc eintragen
echo 'export PATH="/Users/$USER/.crc/bin/oc:$PATH"' >> ~/.zshrc
echo 'export KUBECONFIG=~/.crc/machines/crc/kubeconfig' >> ~/.zshrc
source ~/.zshrc
```

### Verifizieren

```bash
crc status          # CRC VM Status
oc get nodes        # OpenShift Node anzeigen
oc get namespaces   # Alle Namespaces anzeigen
```

---

## Täglicher Workflow

```bash
# CRC starten
crc start

# CRC stoppen
crc stop

# Status prüfen
crc status
```

---

## Wichtige oc Befehle

```bash
# Projekt erstellen (OpenShift = Namespace)
oc new-project phoenix-dev

# Aktuelles Projekt wechseln
oc project phoenix-dev

# App deployen
oc new-app --image=quay.io/openshift-examples/simple-http-server

# Service exponieren (Route erstellen)
oc expose service/simple-http-server

# Route anzeigen
oc get route

# Alle Ressourcen im Namespace
oc get all

# Pods anzeigen
oc get pods

# Logs
oc logs <pod-name>

# Login Status
oc whoami
```

---

## Cluster wechseln (docker-desktop ↔ OpenShift)

```bash
# Alle Contexts anzeigen
kubectx

# Zu docker-desktop wechseln
kubectx docker-desktop

# Zu OpenShift wechseln
export KUBECONFIG=~/.crc/machines/crc/kubeconfig
```

### In k9s zwischen Clustern wechseln

```bash
# OpenShift in k9s öffnen
k9s --kubeconfig ~/.crc/machines/crc/kubeconfig

# Docker Desktop in k9s öffnen
k9s
```

In k9s: **`:ctx`** → zwischen Contexts wechseln

---

## Unterschiede OpenShift vs Kubernetes

| Kubernetes | OpenShift |
|------------|-----------|
| `kubectl` | `oc` (superset von kubectl) |
| Namespace | Project |
| `kubectl create namespace` | `oc new-project` |
| Ingress | Route |
| kein Image Management | ImageStream |
| kein S2I | BuildConfig + S2I |
| Pods können als root laufen | Pods laufen nicht als root (SCC) |
| kein Operator Hub | OperatorHub |
| `kubectl rollout` | `oc rollout` |

---

## OpenShift spezifische Konzepte

### Routes
Routes sind das OpenShift Äquivalent zu Kubernetes Ingress.
Werden automatisch mit dem Format `<service>-<namespace>.apps-crc.testing` erstellt.

```bash
oc expose service/mein-service
oc get route
```

### ImageStreams
OpenShift trackt Images intern — wenn ein neues Image verfügbar ist, wird der Deployment automatisch aktualisiert.

```bash
oc get imagestream
```

### Security Context Constraints (SCC)
OpenShift erlaubt standardmäßig keine Pods die als root laufen.
Statt `nginx:latest` → `nginxinc/nginx-unprivileged` oder Red Hat UBI Images verwenden.

```bash
oc get scc   # alle Security Constraints anzeigen
```

### oc new-app
Erstellt automatisch Deployment + Service + ImageStream in einem Befehl.

```bash
oc new-app --image=quay.io/openshift-examples/simple-http-server
# Erstellt: Deployment, Service, ImageStream
```

---

## Zusammenhang mit ROSA

| CRC Lokal | ROSA/Arbeit |
|-----------|-------------|
| `api.crc.testing` | `api.cluster.firma.de` |
| `*.apps-crc.testing` | `*.apps.cluster.firma.de` |
| kubeadmin | cluster-admin |
| developer | normaler User |
| vfkit VM | AWS EC2 Nodes |
| openshift-monitoring (locked) | openshift-monitoring (locked) |
| CRC Router | HAProxy Router |

---

## Nützliche Aliases (~/.zshrc)

```bash
alias crc-start="crc start"
alias crc-stop="crc stop"
alias crc-status="crc status"
alias ocp="export KUBECONFIG=~/.crc/machines/crc/kubeconfig && echo 'Switched to OpenShift'"
alias k8s="export KUBECONFIG=~/.kube/config && echo 'Switched to docker-desktop'"
```

Nach dem Eintragen:
```bash
source ~/.zshrc
ocp    # zu OpenShift wechseln
k8s    # zu docker-desktop wechseln
```
