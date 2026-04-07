# Incidents & Lösungen — Platform

## Incident 1: llama-server stirbt nach Start
**Problem:** llama-server lädt, meldet "server is listening", stirbt dann sofort
**Ursache:** 8B Fallback auf Port 8082 lief noch und fraß RAM
**Lösung:** Vor 70B Start immer Port 8082 killen: lsof -ti:8082 | xargs kill -9
**Status:** Gelöst

## Incident 2: Port-Forward stirbt nach LaunchAgent Ende
**Problem:** kubectl port-forward als & im Script stirbt wenn Script endet
**Ursache:** Kind-Prozess wird mit Parent beendet
**Lösung:** Eigener LaunchAgent com.yavuz.port-forward mit KeepAlive=true
**Status:** Gelöst

## Incident 3: localhost nicht erreichbar ohne WLAN
**Problem:** localhost:3000 funktioniert nicht ohne WLAN
**Ursache:** DNS-Auflösung von localhost braucht Netzwerk
**Lösung:** echo "127.0.0.1 localhost" >> /etc/hosts
**Status:** Gelöst

## Incident 4: Open WebUI zeigt Modell nicht ohne WLAN
**Problem:** Modell verschwindet aus Dropdown wenn WLAN aus
**Ursache:** Open WebUI URL war MBP-von-Yavuz.fritz.box:8080 — DNS abhängig
**Lösung:** Loopback Alias 10.254.254.254 + URL auf http://10.254.254.254:8080/v1
**Befehl:** sudo ifconfig lo0 alias 10.254.254.254 255.255.255.255
**Persistent in:** port-forward.sh (wird bei jedem Restart neu gesetzt)
**Status:** Gelöst

## Incident 5: sudo braucht Passwort in LaunchAgent
**Problem:** startup.sh kann sudo sysctl und sudo kubectl nicht ausführen
**Ursache:** LaunchAgent hat kein Terminal für Passwort-Eingabe
**Lösung:** /etc/sudoers.d/yavuz-platform mit NOPASSWD für sysctl, kubectl, ifconfig
**Status:** Gelöst

## Incident 6: Merge-Konflikte beim git pull im TurboQuant Fork
**Problem:** git pull scheitert mit vielen Konflikten
**Ursache:** Lokale Commits weichen vom Remote ab
**Lösung:** git merge --abort && git reset --hard origin/feature/turboquant-kv-cache
**Status:** Bekannte Prozedur

## Incident 7: --sparse-v Flag ungültig nach Build-Update
**Problem:** error: invalid argument: --sparse-v
**Ursache:** Flag wurde in neuem Build entfernt, Sparse V ist jetzt automatisch aktiv
**Lösung:** Flag aus .zshrc entfernen — Sparse V läuft als Standard
**Erkenntnis:** "turbo3 sparse V dequant enabled" beim Start = aktiv
**Status:** Gelöst

## Incident 8: Dashboard zeigt keine neuen Commits
**Problem:** intelligence.json wird aus Browser-Cache geladen
**Lösung:** Cache-Busting: fetch('/intelligence.json?t='+Date.now())
**Status:** Gelöst

## Incident 9: Incident Agent skaliert K8s auf 0 beim Startup
**Problem:** Aktion A wird ausgeführt obwohl llama-server nur lädt
**Ursache:** Agent zählt Startup als Crash
**Lösung:** Aktion A deaktiviert, Crash-Counter beim Startup zurücksetzen
**Status:** Gelöst
