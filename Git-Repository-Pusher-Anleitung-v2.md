# Git Repository Pusher für Windows

Dieses Desktop-Tool pusht ein lokales VS-Code-Projekt zu **GitLab oder GitHub**. Es verwendet das lokal installierte Git, erstellt bei Bedarf einen Commit und unterstützt vorhandene Remote-Branches mit abweichender Historie.

## Neue Funktion: abweichende Remote-Historie

Wenn der Ziel-Branch auf GitLab oder GitHub bereits Commits enthält, die lokal fehlen, lehnt Git den normalen Push mit `fetch first` ab.

Das Tool erkennt diese Situation jetzt automatisch und bietet drei Modi:

### 1. Sicher abbrechen

Der Standardmodus. Das Tool überschreibt keine Remote-Commits und bricht mit einer verständlichen Meldung ab.

### 2. Remote-Branch ersetzen

Verwendet einen geschützten Push mit `--force-with-lease`.

Dieser Modus ist für folgenden Fall gedacht:

- Der Remote-Branch wurde über GitLab oder GitHub bearbeitet beziehungsweise geleert.
- Der lokale Projektordner soll künftig der vollständige Inhalt des Branches sein.
- Die Remote-Commits sollen bewusst durch den lokalen Stand ersetzt werden.

Das Tool liest den Remote-Stand zuerst ein und ersetzt ihn nur, wenn er seit diesem Einlesen unverändert geblieben ist. Es verwendet nicht den unkontrollierten Parameter `--force`.

### 3. Remote übernehmen und lokale Änderungen zusammenführen

Das Tool holt den Remote-Branch, führt ihn lokal mit dem aktuellen Stand zusammen und pusht anschließend das Ergebnis.

Bei echten Dateikonflikten bricht der Vorgang ab. Die Konfliktauflösung muss dann manuell in Git oder in einer Entwicklungsumgebung erfolgen.

## Voraussetzungen

- Windows
- Git for Windows
- Python für Windows – nur erforderlich, wenn die Anwendung selbst ausgeführt oder als EXE gebaut wird
- Schreibberechtigung für das Ziel-Repository
- Eine vorhandene GitLab- oder GitHub-Repository-URL

Das Tool erstellt keine neuen Repositories auf GitLab oder GitHub. Das Ziel-Repository muss bereits existieren.

## Starten

Direkt mit Python:

```powershell
python gitlab_push_tool_v2.py
```

Falls der Dateiname geändert wurde:

```powershell
python <dateiname>.py
```

Git muss weiterhin auf dem Rechner installiert sein. Das Tool verwendet die Git-Installation, die über `PATH` gefunden wird.

## EXE erstellen

Mit PyInstaller kann daraus eine Windows-Anwendung erstellt werden:

```powershell
pyinstaller --onefile --windowed --name Git-Repository-Pusher gitlab_push_tool_v2.py
```

Die fertige Datei liegt anschließend im Ordner `dist`.

## GitLab verwenden

Wähle als Plattform **GitLab** und trage die Clone-URL des vorhandenen Projekts ein.

HTTPS-Beispiel:

```text
https://gitlab.example.com/gruppe/projekt.git
```

SSH-Beispiel:

```text
git@gitlab.example.com:gruppe/projekt.git
```

Für eine interne GitLab-Instanz kann die URL beispielsweise so aussehen:

```text
https://gitlab.k8s.nobilia.de/instandhaltung/gitlab-push-tool.git
```

## GitHub verwenden

Wähle als Plattform **GitHub** und trage die Clone-URL des vorhandenen Repositorys ein.

HTTPS-Beispiel:

```text
https://github.com/dein-konto/projekt.git
```

SSH-Beispiel:

```text
git@github.com:dein-konto/projekt.git
```

## Anmeldung

### HTTPS

Das Tool fragt selbst kein Passwort und keinen Token ab. Git verwendet die auf dem Rechner eingerichtete Anmeldung, zum Beispiel den Git Credential Manager.

Wenn GitHub oder GitLab einen Token verlangt, muss dieser über die normale Git-Anmeldung beziehungsweise den Credential Manager eingerichtet werden. Der Token wird nicht in die Repository-URL geschrieben.

### SSH

Mit einem eingerichteten SSH-Schlüssel kann die SSH-Clone-URL verwendet werden.

GitHub testen:

```powershell
ssh -T git@github.com
```

GitLab testen:

```powershell
ssh -T git@gitlab.k8s.nobilia.de
```

## Verwendung

1. **Projektordner auswählen** – wähle den lokalen Ordner aus, den du pushen möchtest.
2. **GitLab** oder **GitHub** auswählen.
3. Die Clone-URL des vorhandenen Ziel-Repositorys eintragen.
4. Den Ziel-Branch eintragen, zum Beispiel `main` oder `master`.
5. Eine Commit-Nachricht eintragen.
6. Optional einen Tag und eine Tag-Nachricht eintragen.
7. Optional **Verbindung prüfen** anklicken.
8. Bei einer abweichenden Remote-Historie das gewünschte Verhalten auswählen.
9. **Commit erstellen und pushen** anklicken und bestätigen.

## Empfohlener Ablauf für ein über die Weboberfläche geleertes Repository

Wenn der Ziel-Branch in GitLab oder GitHub über die Weboberfläche geleert wurde und der lokale Ordner anschließend wieder vollständig hochgeladen werden soll:

1. Ziel-Branch auswählen, zum Beispiel `master`.
2. Bei **Verhalten bei abweichender Remote-Historie** auswählen:

   ```text
   Remote-Branch ersetzen (mit --force-with-lease)
   ```

3. Den Push bestätigen.
4. Das Tool liest den Remote-Branch ein.
5. Die lokalen Dateien werden mit `git add -A` erfasst.
6. Falls nötig wird ein Commit erstellt.
7. Der Ziel-Branch wird mit `--force-with-lease` aktualisiert.

Damit wird der Remote-Branch durch den aktuellen lokalen Stand ersetzt, sofern zwischen Prüfung und Push niemand den Remote-Branch verändert hat.

## Wie das Tool mit Branches arbeitet

Das Tool verwendet den im Formular angegebenen Ziel-Branch. Vor dem Push:

- wird `origin` auf die eingegebene URL gesetzt;
- wird der Remote-Ziel-Branch mit `git ls-remote` gelesen;
- wird der Remote-Branch lokal mit `git fetch` eingelesen;
- wird der lokale Ziel-Branch auf den aktuellen lokalen Stand gesetzt;
- werden Änderungen mit `git add -A` vorgemerkt;
- wird bei Änderungen ein Commit erstellt;
- wird normal oder geschützt mit `--force-with-lease` gepusht.

Das lokale Repository muss nicht vorher geklont worden sein. Wenn im Projektordner noch kein `.git`-Ordner vorhanden ist, führt das Tool `git init` aus.

## Tags

Wenn ein Tag eingetragen wurde, führt das Tool diese Schritte aus:

1. Dateien hinzufügen und committen, falls Änderungen vorhanden sind.
2. Den Ziel-Branch pushen.
3. Den Tag am aktuellen Commit anlegen.
4. Den Tag zum Remote pushen.

Ein bereits lokal oder remote vorhandener Tag wird nicht überschrieben. In diesem Fall kann der Branch trotzdem bereits erfolgreich gepusht worden sein; das Tool meldet den Vorgang dann als teilweise erfolgreich.

## Geschützte Branches

Wenn `main` oder `master` auf GitLab oder GitHub geschützt ist, kann ein Push – insbesondere ein Force-with-lease-Push – serverseitig abgelehnt werden.

Dann muss in den Repository-Einstellungen entweder:

- der Force-Push für diesen Branch erlaubt werden;
- der Branch vorübergehend weniger streng geschützt werden;
- oder ein neuer Branch gepusht und anschließend über einen Merge Request beziehungsweise Pull Request zusammengeführt werden.

Das Tool kann serverseitige Branch-Regeln nicht umgehen.

## Sicherheitshinweise

- Der Standardmodus überschreibt keine Remote-Commits.
- Ein Überschreiben ist nur über die ausdrücklich ausgewählte Option möglich.
- Auch dann verwendet das Tool `--force-with-lease`, nicht `--force`.
- Das Tool fragt keine Zugangsdaten ab.
- Zugangsdaten und Tokens werden nicht in die URL geschrieben.
- Die Ausgabe blendet URL-Zugangsdaten aus, falls versehentlich eine URL mit Benutzerinformationen eingetragen wurde.
- `git add -A` nimmt alle nicht durch `.gitignore` ausgeschlossenen Dateien im Projektordner auf.
- Vor dem Push sollte eine passende `.gitignore` vorhanden sein, damit keine Passwörter, virtuellen Umgebungen, Build-Ordner oder lokalen Einstellungen hochgeladen werden.

## Typische Fehlermeldungen

### `fetch first`

Der Remote-Branch enthält Commits, die lokal fehlen. Wähle entweder:

- **Sicher abbrechen**, wenn die Remote-Commits erhalten bleiben sollen;
- **Remote-Branch ersetzen**, wenn der lokale Stand bewusst an die Stelle des Remote-Stands treten soll;
- **Remote übernehmen und lokale Änderungen zusammenführen**, wenn beide Seiten erhalten bleiben sollen.

### `non-fast-forward`

Der lokale Branch ist nicht direkt auf dem aktuellen Remote-Stand aufgebaut. Das Tool behandelt diesen Fall wie eine abweichende Historie und verwendet die ausgewählte Konfliktstrategie.

### `protected branch hook declined`

Der Ziel-Branch ist serverseitig geschützt. Das muss in den Branch-Regeln von GitLab oder GitHub angepasst werden, oder der Push muss über einen neuen Branch und einen Merge-/Pull-Request erfolgen.

### `Authentication failed`

Die lokale Git-Anmeldung ist ungültig oder fehlt. Teste die URL mit **Verbindung prüfen** und richte anschließend Git Credential Manager oder SSH ein.

### `repository not found`

Prüfe die Clone-URL, den Gruppennamen beziehungsweise Benutzernamen und deine Berechtigung für das Repository.
