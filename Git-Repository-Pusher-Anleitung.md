# Git Repository Pusher für Windows

Dieses Desktop-Tool schiebt ein lokales VS-Code-Projekt wahlweise zu **GitLab oder GitHub**. Es verwendet das lokal installierte Git und fragt selbst keine Passwörter oder Tokens ab.

## Voraussetzungen

- Windows
- Git for Windows
- Python für Windows – nur erforderlich, wenn du die Anwendung selbst als EXE baust
- Berechtigung für das jeweilige Ziel-Repository

## EXE erstellen

1. Lade das Paket herunter und entpacke es.
2. Starte `build_gitlab_pusher.bat` per Doppelklick.
3. Falls erforderlich, installiert der Builder PyInstaller.
4. Die fertige Anwendung liegt anschließend im Ordner `dist` als `Git-Repository-Pusher.exe`.

Git muss auf dem Rechner weiterhin installiert sein, weil die Anwendung Git für Commit und Push verwendet.

## GitLab verwenden

Als Plattform **GitLab** auswählen und die Clone-URL des Zielprojekts eintragen, zum Beispiel:

- HTTPS: `https://gitlab.k8s.nobilia.de/instandhaltung/projektname.git`
- SSH: `git@gitlab.k8s.nobilia.de:instandhaltung/projektname.git`

## GitHub verwenden

Als Plattform **GitHub** auswählen und die Clone-URL des GitHub-Repositories eintragen, zum Beispiel:

- HTTPS: `https://github.com/dein-konto/projektname.git`
- SSH: `git@github.com:dein-konto/projektname.git`

Bei GitHub muss das Repository normalerweise bereits existieren. Das Tool erstellt keine GitHub-Repositories über die API, sondern pusht in ein vorhandenes Repository.

## Anmeldung

### HTTPS

Git verwendet die auf dem Rechner konfigurierte Anmeldung, zum Beispiel Git Credential Manager. Wenn Git nach Zugangsdaten fragt, verwende die für deine Plattform vorgesehenen Zugangsdaten beziehungsweise einen persönlichen Access Token, falls dies erforderlich ist. Das Tool speichert keinen Token und schreibt keinen Token in die Repository-URL.

### SSH

Wenn ein SSH-Schlüssel eingerichtet ist, kann die SSH-Clone-URL verwendet werden. Die Verbindung kann vorher im Terminal getestet werden:

```powershell
ssh -T git@github.com
ssh -T git@gitlab.k8s.nobilia.de
```

## Verwendung

1. **Projektordner auswählen** – den Ordner öffnen, den du in VS Code bearbeitest.
2. Plattform **GitLab** oder **GitHub** auswählen.
3. Die Clone-URL des vorhandenen Ziel-Repository eintragen.
4. Ziel-Branch festlegen, meistens `main` oder bei älteren Projekten `master`.
5. Commit-Nachricht eintragen.
6. Optional einen Tag eintragen, beispielsweise `v1.0.0`.
7. Optional eine Tag-Nachricht eintragen. Ohne Tag-Nachricht wird ein einfacher Tag angelegt; mit Nachricht ein annotierter Tag.
8. **Verbindung prüfen** anklicken.
9. **Commit erstellen und pushen** anklicken und bestätigen.

## Tags

Wenn ein Tag eingetragen ist, führt das Tool diese Schritte aus:

1. Dateien hinzufügen und committen, falls Änderungen vorhanden sind.
2. Den Branch zum ausgewählten Git-Host pushen.
3. Den Tag am aktuellen Commit anlegen.
4. Den Tag ebenfalls zum Remote pushen.

Ein bereits lokal vorhandener Tag wird aus Sicherheitsgründen nicht überschrieben. Das Tool führt keinen Force-Push aus.

## Wichtige Hinweise

- Das Tool führt `git init` aus, wenn der Projektordner noch kein Git-Repository ist.
- Es fügt mit `git add -A` alle Dateien im Projektordner hinzu. Lege vorher eine `.gitignore` an, damit keine Passwörter, virtuellen Umgebungen, Build-Ordner oder lokalen Einstellungen hochgeladen werden.
- Das Tool setzt `origin` auf die eingetragene URL.
- Bei einem bereits befüllten Remote-Repository kann der Push wegen unterschiedlicher Historien abgelehnt werden. Das ist absichtlich sicherer, als automatisch einen Force-Push auszuführen.
- Bei Netzlaufwerken berücksichtigt das Tool die Windows-UNC-Pfade und die Git-Sicherheitsprüfung.
