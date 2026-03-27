# TLS mit cert-manager und mkcert

## Überblick
Lokale HTTPS Zertifikate ohne Browser-Warnung mit mkcert als CA und cert-manager als automatischen Zertifikats-Manager.

## Voraussetzungen
- Kubernetes Cluster läuft
- mkcert installiert (`brew install mkcert`)
- cert-manager installiert

## Schritt 1 — mkcert CA installieren
```bash
mkcert -install
```
Erstellt eine lokale CA und installiert sie im Mac Keychain — Browser vertrauen ihr automatisch.

## Schritt 2 — cert-manager installieren
```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.17.1/cert-manager.yaml
kubectl get pods -n cert-manager -w
```
Warten bis alle Pods Running sind.

## Schritt 3 — mkcert CA als Secret in cert-manager laden
```bash
kubectl create secret tls mkcert-ca \
  --cert="$HOME/Library/Application Support/mkcert/rootCA.pem" \
  --key="$HOME/Library/Application Support/mkcert/rootCA-key.pem" \
  -n cert-manager
```

## Schritt 4 — ClusterIssuer erstellen
```bash
cat > /tmp/clusterissuer.yaml << 'YAML'
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: mkcert-issuer
spec:
  ca:
    secretName: mkcert-ca
YAML

kubectl apply -f /tmp/clusterissuer.yaml
kubectl get clusterissuer mkcert-issuer
```
Warten bis READY: True

## Schritt 5 — Certificate für Domain erstellen
```bash
cat > /tmp/certificate.yaml << 'YAML'
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: ollama-tls
  namespace: ollama
spec:
  secretName: ollama-cert-tls
  issuerRef:
    name: mkcert-issuer
    kind: ClusterIssuer
  dnsNames:
    - ollama.local
YAML

kubectl apply -f /tmp/certificate.yaml
kubectl get certificate -n ollama
```
cert-manager erstellt das Secret automatisch.

## Schritt 6 — Ingress konfigurieren
```yaml
annotations:
  cert-manager.io/cluster-issuer: "mkcert-issuer"
spec:
  tls:
    - hosts:
        - ollama.local
      secretName: ollama-cert-tls
```
cert-manager erkennt die Annotation und erstellt das Certificate Objekt automatisch.

## Wie funktioniert das in Produktion?
Auf ROSA oder einem echten Cluster tauschst du nur den Issuer aus:
```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: deine@email.de
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
      - http01:
          ingress:
            class: nginx
```

Der Rest bleibt identisch — nur `mkcert-issuer` wird zu `letsencrypt-prod`.

## Warum keine Browser-Warnung?
- mkcert CA ist im Mac Keychain gespeichert
- Browser fragt Mac: "Kenne ich diese CA?" → Ja ✅
- Zertifikat wird vertraut → keine Warnung
