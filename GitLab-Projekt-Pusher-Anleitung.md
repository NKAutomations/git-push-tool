# GitLab-Projekt-Pusher für Windows

Dieses kleine Desktop-Tool übergibt ein lokales VS-Code-Projekt an ein vorhandenes GitLab-Repository. Es verwendet das lokal installierte Git und fragt selbst keine Passwörter oder Tokens ab.

## Voraussetzungen

1. **Git for Windows** ist installiert: <https://git-scm.com/download/win>
2. Du hast im nobilia-GitLab ein leeres oder passendes Repository angelegt.
3. Du kennst die **Clone-URL** des Repositories. Sie steht in GitLab unter **Code** und sieht typischerweise so aus:
   - HTTPS: `https://gitlab.k8s.nobilia.de/instandhaltung/projektname.git`
   - SSH: `git@gitlab.k8s.nobilia.de:instandhaltung/projektname.git`

## Starten

Im Ordner mit dem Tool PowerShell öffnen und ausführen:

```powershell
python .\gitlab_push_tool.py
```

Falls `python` nicht gefunden wird, kann je nach Installation auch `py` funktionieren:

```powershell
py .\gitlab_push_tool.py
```

## Anmeldung

### Empfehlung: SSH

Wenn eure IT SSH für GitLab freigibt, ist das für regelmäßige Nutzung meist am bequemsten. In GitLab findest du deinen Schlüsselbereich unter deinem Profil. Die SSH-Clone-URL beginnt mit `git@`.

Vor dem ersten Push kann die Verbindung getestet werden:

```powershell
ssh -T git@gitlab.k8s.nobilia.de
```

### HTTPS

Bei einer HTTPS-URL verwendet Git die auf dem Rechner konfigurierte Git-/Windows-Anmeldung. Das Tool legt keinen Token in der URL ab. Wenn Git beim Push nach Zugangsdaten fragt, verwende die von eurer GitLab-Instanz vorgesehenen Anmeldedaten beziehungsweise einen persönlichen Access Token, falls eure IT das so eingerichtet hat.

## Verwendung

1. **Projektordner auswählen** – den Ordner öffnen, den du in VS Code bearbeitest.
2. Die **Clone-URL** des vorhandenen GitLab-Repositories eintragen.
3. Branch festlegen, meistens `main`.
4. Commit-Nachricht eintragen.
5. Optional zuerst **Verbindung prüfen** anklicken.
6. **Commit erstellen und pushen** anklicken und bestätigen.

## Wichtige Hinweise

- Das Tool führt `git init` aus, wenn der Projektordner noch kein Git-Repository ist.
- Es fügt mit `git add -A` alle Dateien im Projektordner hinzu. Lege deshalb vorher eine `.gitignore` an, damit keine Passwörter, virtuellen Umgebungen, Build-Ordner oder lokalen Einstellungen hochgeladen werden.
- Das Tool setzt `origin` auf die eingetragene URL und pusht in den gewählten Branch.
- Bei einem bereits befüllten Remote-Repository kann der Push wegen unterschiedlicher Historien abgelehnt werden. Das ist absichtlich sicherer, als automatisch einen Force-Push auszuführen.
