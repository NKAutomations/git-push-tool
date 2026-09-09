# Git Repository Pusher

Ein schlanker Windows-Assistent, um ein lokales Projekt kontrolliert zu GitLab oder GitHub zu pushen.

Die Anwendung verwendet die lokal installierte Git-Installation und fragt keine Zugangsdaten ab. Die Anmeldung erfolgt wie gewohnt über Git Credential Manager oder einen eingerichteten SSH-Schlüssel.

## Funktionen

- Lokalen Projektordner auswählen
- GitLab oder GitHub als Ziel auswählen
- HTTPS- oder SSH-Repository-URL verwenden
- Lokales Repository bei Bedarf automatisch initialisieren
- Ziel-Branch festlegen
- Commit erstellen und pushen
- Optionalen Git-Tag erstellen und pushen
- Umgang mit abweichender Remote-Historie auswählen
- Sicherer Push-Modus mit `--force-with-lease`
- Verbindung zum Repository prüfen
- Responsive Oberfläche für kleine Fenster und Bildschirme
- Vertikales Scrollen bei geringer Fensterhöhe
- README-Datei des ausgewählten Projekts öffnen
- README im Markdown-Editor bearbeiten
- README in einer lesbaren Vorschau anzeigen
- Neue `README.md` anlegen, wenn noch keine vorhanden ist

## Voraussetzungen

- Windows
- Git for Windows
- Eine vorhandene GitLab- oder GitHub-Repository-URL
- Schreibberechtigung für das Ziel-Repository
- Python für den direkten Start oder den EXE-Build
- PyInstaller nur zum Erstellen der EXE-Datei

Das Ziel-Repository muss bereits auf GitLab oder GitHub existieren. Das Tool erstellt keine neuen Remote-Repositories.

## Start mit Python

Lege die Datei `gitlab_push_tool_v2.py` zusammen mit den übrigen Dateien in einen Ordner und starte sie mit:

```text
python gitlab_push_tool_v2.py
```

Alternativ unter Windows:

```text
py -3 gitlab_push_tool_v2.py
```

## EXE erstellen

Stelle sicher, dass Python und PyInstaller in der verwendeten Python-Umgebung verfügbar sind. Starte anschließend:

```text
build_gitlab_pusher.bat
```

Die fertige Anwendung wird hier erzeugt:

```text
dist\Git-Repository-Pusher.exe
```

## Verwendung

1. Projektordner auswählen.
2. Zielplattform auswählen.
3. Clone-URL des vorhandenen Repositorys eintragen.
4. Ziel-Branch eintragen, zum Beispiel `main` oder `master`.
5. Commit-Nachricht eintragen.
6. Optional einen Tag und eine Tag-Nachricht eintragen.
7. Optional die Verbindung prüfen.
8. Den Umgang mit einer abweichenden Remote-Historie auswählen.
9. Den Push bestätigen.

## Umgang mit abweichender Remote-Historie

Wenn der Ziel-Branch auf GitLab oder GitHub Commits enthält, die lokal fehlen, kann ein normaler Push abgelehnt werden. Das Tool bietet dafür drei Modi:

### Sicher abbrechen

Der Vorgang wird abgebrochen. Remote-Commits werden nicht überschrieben.

### Remote-Branch ersetzen

Der lokale Stand wird mit `--force-with-lease` zum Remote-Branch gepusht.

Der Remote-Stand wird vor dem Push gelesen. Das Überschreiben erfolgt nur, wenn sich der Remote-Branch seit dieser Prüfung nicht verändert hat.

Dieser Modus sollte nur verwendet werden, wenn der lokale Stand bewusst an die Stelle des Remote-Stands treten soll.

### Remote übernehmen und lokale Änderungen zusammenführen

Der Remote-Branch wird lokal zusammengeführt und anschließend gepusht.

Bei echten Dateikonflikten wird der Vorgang abgebrochen. Die Konflikte müssen anschließend manuell in Git oder einer Entwicklungsumgebung gelöst werden.

## README-Editor

Über den Button **README öffnen** kann die README-Datei des ausgewählten Projektordners geöffnet werden.

### Vorhandene README

Das Tool erkennt unter anderem folgende Dateinamen:

- `README.md`
- `readme.md`
- `Readme.md`
- `README.MD`

Die gefundene Datei wird automatisch geladen.

### Neue README

Wenn noch keine README-Datei vorhanden ist, öffnet der Editor eine neue Vorlage. Beim Speichern wird sie als `README.md` im ausgewählten Projektordner angelegt.

### Bearbeiten und Vorschau

Der Editor bietet zwei Modi:

- **Bearbeiten**: Markdown-Text direkt ändern
- **Vorschau**: Überschriften, Listen, Codeblöcke, Zitate und Trennlinien lesbar darstellen

Die Vorschau ist eine integrierte, vereinfachte Markdown-Darstellung für den schnellen Überblick. Die originale Markdown-Datei bleibt beim Speichern unverändert in ihrer Markdown-Struktur erhalten.

Ungespeicherte Änderungen werden beim Schließen des Editors erkannt. Das Tool fragt dann, ob die Änderungen gespeichert werden sollen.

Die README wird nach dem Speichern automatisch vom normalen Git-Ablauf erfasst, da der Push-Vorgang mit `git add -A` arbeitet.

## Responsive Oberfläche

Die Oberfläche passt sich an kleinere Fenster an:

- Formularfelder wechseln auf einspaltige Darstellung.
- Buttons werden untereinander und über die verfügbare Breite angezeigt.
- Der Button zur Projektordner-Auswahl bleibt erreichbar.
- Lange Texte werden automatisch umgebrochen.
- Bei geringer Fensterhöhe kann vertikal gescrollt werden.
- Die Mindestfenstergröße beträgt 420 × 540 Pixel.

## Git-Anmeldung

### HTTPS

Bei HTTPS verwendet Git die lokal eingerichtete Anmeldung, zum Beispiel den Git Credential Manager.

Das Tool fragt selbst kein Passwort und keinen Token ab. Zugangsdaten sollten niemals in die Repository-URL geschrieben werden.

### SSH

Bei SSH muss ein passender SSH-Schlüssel eingerichtet sein.

GitHub-Verbindung testen:

```text
ssh -T git@github.com
```

GitLab-Verbindung testen:

```text
ssh -T git@gitlab.com
```

Für interne GitLab-Installationen muss der jeweilige interne Hostname verwendet werden.

## Tags

Wenn ein Tag eingetragen wurde, führt das Tool nach dem Branch-Push folgende Schritte aus:

1. Prüfen, ob der Tag lokal bereits vorhanden ist.
2. Prüfen, ob der Tag remote bereits vorhanden ist.
3. Den Tag lokal erstellen.
4. Den Tag zum Remote pushen.

Bereits vorhandene Tags werden nicht überschrieben. In diesem Fall kann der Branch trotzdem erfolgreich gepusht worden sein.

## Geschützte Branches

GitLab und GitHub können Branches serverseitig schützen. Ein Push auf einen geschützten Branch kann dann abgelehnt werden.

Das Tool kann diese Regeln nicht umgehen. In diesem Fall kann je nach Repository-Konfiguration Folgendes erforderlich sein:

- Push-Regeln des Branches anpassen
- Force-Push für den Branch erlauben
- neuen Branch erstellen
- Änderungen über Merge Request oder Pull Request zusammenführen

## Sicherheitshinweise

- Der Standardmodus überschreibt keine Remote-Commits.
- Ein Überschreiben ist nur über die ausdrücklich ausgewählte Option möglich.
- Das Tool verwendet `--force-with-lease`, nicht `--force`.
- Zugangsdaten werden nicht abgefragt.
- Tokens und Passwörter gehören nicht in Repository-URLs.
- Git-Ausgaben mit URL-Zugangsdaten werden für die Anzeige maskiert.
- `git add -A` erfasst alle Dateien, die nicht durch `.gitignore` ausgeschlossen sind.
- Vor dem Push sollte eine passende `.gitignore` vorhanden sein.
- Prüfe besonders Dateien wie `.env`, private Schlüssel, Zugangsdaten und lokale Konfigurationen.

## Typische Probleme

### `fetch first` oder `non-fast-forward`

Der Remote-Branch enthält Commits, die lokal fehlen. Wähle den passenden Modus für die gewünschte Vorgehensweise.

### `Authentication failed`

Die lokale Git-Anmeldung fehlt oder ist ungültig. Prüfe Credential Manager, SSH-Schlüssel und Repository-URL.

### `repository not found`

Prüfe Repository-URL, Benutzer- oder Gruppennamen sowie die Zugriffsberechtigung.

### `protected branch hook declined`

Der Ziel-Branch ist serverseitig geschützt. Verwende gegebenenfalls einen neuen Branch und anschließend einen Merge Request oder Pull Request.

### Commit kann nicht erstellt werden

Git benötigt eine konfigurierte Identität. Prüfe insbesondere:

```text
git config --global user.name
 git config --global user.email
```

Falls noch keine Werte hinterlegt sind:

```text
git config --global user.name "Dein Name"
git config --global user.email "deine-adresse@example.com"
```

## Dateien im Paket

```text
gitlab_push_tool_v2.py       Hauptanwendung
Git-Repository-Pusher.spec   PyInstaller-Spezifikation
build_gitlab_pusher.bat      Build-Skript für die EXE
README.md                    Dokumentation
```

## Hinweis zur Nutzung

Das Tool ist für einen einfachen und kontrollierten Push-Ablauf gedacht. Prüfe vor einem Push immer Ziel-Repository, Branch und Commit-Nachricht. Bei einem Force-with-lease-Push sollte zusätzlich sichergestellt werden, dass der Remote-Branch bewusst ersetzt werden soll.
