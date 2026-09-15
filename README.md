# Git Repository Pusher – Umsetzung und Startanleitung

## Lieferstatus

Der Auftrag ist als modulare Python-/PySide6-Implementierung umgesetzt. Das Quellcodepaket enthält Anwendung, Git-Kern, GitHub-/GitLab-Provider, Markdown-Editor, Upload-Verarbeitung, Tests und portable Windows-Build-Dateien. Es wurde nichts in das öffentliche Repository geschrieben und kein Release live veröffentlicht.

**Validierung:** 39 automatisierte Tests entdeckt, davon **36 bestanden und 3 GUI-Tests übersprungen**. Die Git-Integrationstests verwenden echte lokale Arbeitsverzeichnisse und Bare-Repositories. HTTP-/Provider-Tests verwenden simulierte Antworten. Alle Python-Dateien wurden auf Syntax geprüft.

**Keine Produktionsfreigabe:** PySide6 ist in der verwendeten Linux-Umgebung nicht installiert. Deshalb sind die Oberfläche, Windows-spezifische Pfade, Credential Manager, SSH-Agent, Windows-EXE und echte GitHub-/GitLab-Veröffentlichungen noch nicht praktisch abgenommen. Das Paket enthält Quellcode, keine vorgetäuscht fertig gebaute EXE. Vor produktiver Nutzung den Abschnitt „Abnahme“ vollständig durchführen.

## Analyse und Architekturentscheidung

Ausgangspunkt ist [NKAutomations/git-push-tool](https://github.com/NKAutomations/git-push-tool). Die ausgewerteten Quellen umfassen die Hauptanwendung, README, Build-Spezifikation, Build-Skript sowie README-/Responsive-Änderungsnotizen. Die Webansicht erlaubte keine verlässliche vollständige rekursive Analyse sämtlicher Repository-Artefakte und Build-Ausgaben; eine vollständige lokale Bestandsprüfung wird deshalb nicht behauptet.

Wesentliche Befunde:

- Git, Tkinter-Oberfläche und README-Funktionalität lagen überwiegend in einer Hauptdatei.
- Das automatische `checkout -B` konnte einen bestehenden lokalen Branch versetzen.
- Die Redaktion sensibler Git-Ausgaben war nicht durchgängig.
- Die PyInstaller-Spezifikation enthielt einen festen lokalen Windows-Pfad.
- Release-Provider, Upload-Zustände und API-Authentifizierung benötigten eigenständige Schichten.

Die neue Implementierung ersetzt die Oberfläche durch PySide6 und trennt Verantwortlichkeiten. Sie ist eine zusammenhängende Ersatzversion, kein gegen einen lokal ausgecheckten, festgehaltenen Upstream-Commit erzeugter Patch. Bestehende projektspezifische Anpassungen vor der Übernahme vergleichen.

### Module

| Datei | Aufgabe |
|---|---|
| `gitlab_push_tool_v2.py` | Kompatibler Startpunkt unter dem bisherigen Namen |
| `pusher/gui.py` | Projektansicht, Release-Dialog, Dateien, Ergebnisanzeige |
| `pusher/git_service.py` | Git-Initialisierung, Branch-Prüfung, Commit, Push, Merge, Tags |
| `pusher/models.py` | Optionen, Fehler und getrennte Teilergebnisse |
| `pusher/security.py` | Repository-URL-Prüfung und Redaktion |
| `pusher/auth.py` | API-Token aus Eingabe, Umgebung oder GitHub CLI |
| `pusher/http_client.py` | HTTPS, Host-Bindung, Timeouts, Upload-Stream |
| `pusher/providers.py` | Gemeinsame Provider-Schnittstelle und GitHub-/GitLab-Implementierungen |
| `pusher/assets.py` | Dateiprüfung, Snapshots, SHA-256, ZIP, Upload-Einzelstatus |
| `pusher/editor.py` | Gemeinsamer Markdown-Editor für README und Release Notes |
| `pusher/jobs.py` | Hintergrundjobs und Abbruchsignale |
| `pusher/theme.py` | Helle/dunkle Gestaltung und Fokuszustände |
| `tests/` | Lokale Git-, Security-, API-, Upload- und Qt-Smoke-Tests |

## Übernahme in das Repository

1. Das bestehende Repository lokal sichern und einen eigenen Entwicklungsbranch erstellen.
2. Den Inhalt des Ordners `git-push-tool-modernized` aus dem ZIP in die lokale Repository-Wurzel übernehmen. Die eigene `.git`-Struktur bleibt unangetastet.
3. Vorhandene Dateien mit gleichem Namen vergleichen: insbesondere Startdatei, README, Build-Skript, PyInstaller-Spezifikation und `.gitignore`.
4. Bereits versionierte `build/`- und `dist/`-Artefakte gegebenenfalls bewusst aus der Versionsverwaltung entfernen. Die neue `.gitignore` allein entfernt keine bereits versionierten Dateien.
5. Umgebung einrichten, Tests ausführen und Anwendung zunächst ausschließlich mit einem Test-Repository verwenden.
6. Erst nach Abnahme die Änderungen selbst committen und pushen.

Die Übernahme ändert keine Git-Remotes automatisch. Das Paket enthält keine Zugangsdaten.

## Voraussetzungen

- Windows für den vorgesehenen Desktopbetrieb und EXE-Build.
- Python **3.12 x64** als festgelegte Build-Basis.
- Git for Windows im `PATH`, einschließlich eingerichteter Benutzeridentität.
- Ein bereits existierendes GitHub-/GitLab-Remote-Repository. Das Tool erstellt keine neuen Remote-Repositories.
- Git-Anmeldung über Credential Manager oder SSH-Agent.
- Für Releases zusätzlich eine API-Anmeldung mit ausreichenden projektbezogenen Rechten.

`requirements.txt` und `requirements-build.txt` fixieren direkte und bekannte transitive Abhängigkeiten auf eine konkrete Basis. Das ist **keine Behauptung aktueller oder sicherheitsgeprüfter neuester Versionen**, kein Hash-Lock und keine Garantie bitidentischer Builds. Vor Verteilung Abhängigkeiten im eigenen Freigabeprozess auf Sicherheitsupdates prüfen. Python-Patchversion, Wheels und Betriebssystem für streng reproduzierbare Builds zusätzlich festhalten.

### Git-Identität vor der ersten Nutzung einmalig einrichten

Vor der ersten Nutzung sollte die Git-Identität auf dem Rechner beziehungsweise in der Windows-VM bewusst eingerichtet und geprüft werden. Ein Repository kann bereits funktionieren, wenn `user.name` und `user.email` dort lokal hinterlegt sind. In einem zweiten oder neu geklonten Repository fehlen diese Werte jedoch möglicherweise wieder; dann scheitern Commit-Vorgänge oder automatische Erkennungsversuche.

Git unterscheidet zwischen einer **lokalen Repository-Konfiguration** und einer **globalen Konfiguration**:

- **Lokal** gesetzte Werte gelten nur im aktuellen Repository.
- **Global** gesetzte Werte gelten für alle zukünftigen Projekte des aktuellen Windows-Benutzers auf diesem Rechner beziehungsweise in dieser VM.

Für eine Windows-VM ist die globale Konfiguration in der Regel die sinnvollste Grundeinstellung, damit neue Projekte nicht erneut an einer fehlenden Git-Identität scheitern.

```powershell
git config --global user.email "ihre.github.email@beispiel.de"
git config --global user.name "Ihr Name oder GitHub-Username"
```

Zur Prüfung ohne weitere Änderung eignen sich zum Beispiel diese Befehle:

```powershell
git config --global user.name
git config --global user.email
git config --list --show-origin
```

Es müssen echte persönliche Daten verwendet werden. `user.name` muss nicht zwingend dem GitHub-Username entsprechen; `user.email` sollte aber sinnvollerweise zu einem verifizierten Konto beziehungsweise zur gewünschten Commit-Zuordnung bei GitHub oder GitLab passen.

Die Git-Identität ersetzt nicht automatisch die Authentifizierung am GitHub-/GitLab-Remote. Credential Manager, SSH-Agent oder andere Zugangsdaten bleiben weiterhin separat erforderlich.

Falls die Identität absichtlich nur für ein einzelnes Repository gesetzt werden soll, erfolgt das ohne `--global` direkt im Projektordner:

```powershell
cd C:\Pfad\Zum\Projekt
git config user.email "ihre.github.email@beispiel.de"
git config user.name "Ihr Name oder GitHub-Username"
```

Keine Zugangsdaten, Tokens oder sonstigen privaten Werte in die Konfiguration oder in Projektdateien eintragen.

## Installation auf dem eigenen Windows-Rechner

Die folgenden Befehle sind für den eigenen Rechner mit Paketquellenzugriff bestimmt; in der Erstellungsumgebung wurden keine Pakete nachinstalliert.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe gitlab_push_tool_v2.py
```

Für den reinen Python-Betrieb genügt `requirements.txt` statt der Build-Anforderungen. Nach Einrichtung startet alternativ `start.bat` die Anwendung. Auch `python -m pusher` ist möglich, wenn die passende Umgebung aktiv ist.

### EXE bauen

```powershell
.\build_gitlab_pusher.bat
```

Das Skript verwendet relative Pfade, prüft die Umgebung, führt Tests aus und baut über `Git-Repository-Pusher.spec` eine Onefile-/Windowed-EXE. Es nutzt `pushd`, damit auch der Aufruf aus einem UNC-Verzeichnis unterstützt wird. Es installiert selbst nichts und löscht nicht pauschal bestehende Ausgabeordner.

Erwartete neue Build-Ausgaben:

- `dist/Git-Repository-Pusher.exe`
- `dist/SHA256SUMS.txt`
- `dist/build-environment.txt`

Ein fehlgeschlagener Build kann eine ältere EXE im Ausgabeordner stehen lassen: nur bei erfolgreichem Skriptende und geprüften neuen Artefakten freigeben. Die EXE benötigt weiterhin eine lokale Git-Installation. Sie ist nicht codesigniert. Vor öffentlicher Verteilung Qt/PySide-Lizenzpflichten, Drittanbieterhinweise, Signierung und Windows-Sicherheitsprüfung klären.

## Bedienablauf

### Projekt → Commit → Tag

1. Projektordner und Plattform auswählen.
2. HTTPS- oder SSH-Repository-URL und Ziel-Branch eingeben.
3. Bei abweichendem SSH-/Web-Host die HTTPS-Web-Origin ergänzen. Diese bestimmt den API-Empfänger und muss sorgfältig geprüft werden.
4. Verbindung prüfen. Ein lesbares Repository bestätigt noch keine Schreib- oder API-Berechtigung.
5. README öffnen oder anlegen, bearbeiten, Vorschau ansehen und speichern.
6. Änderungen prüfen und eine Commit-Nachricht eingeben.
7. Gewünschten Umgang mit zusätzlicher Remote-Historie auswählen.
8. Optional Tag und Tag-Nachricht eingeben; bei Bedarf das Öffnen der Release-Ansicht aktivieren.
9. „Committen und pushen“ bestätigen.
10. Die Einzelstatus für Commit, Branch-Push und Tag-Push prüfen.

Die Änderungsprüfung kann ein noch fehlendes lokales Repository initialisieren. Der Commit umfasst `git add -A`: neue Dateien, Änderungen und Löschungen. `.gitignore`, Zugangsdaten, große Binärdateien und versehentlich ausgewählte Projektordner vorher kontrollieren. Das Tool ist kein Secret-Scanner.

### Remote-Historie

- **Sicher stoppen:** Ein normaler Push überschreibt keine zusätzliche Remote-Historie.
- **Integrieren:** Der geprüfte Remote-Stand wird gemergt. Unabhängige Historien werden nur mit zusätzlicher Auswahl erlaubt. Merge-Konflikte bleiben zur manuellen Auflösung bestehen; das Tool führt keinen versteckten Reset aus.
- **Ersetzen:** Erst nach ausdrücklicher Bestätigung wird ein `--force-with-lease=refs/heads/BRANCH:ERWARTETE_SHA` verwendet. Auch ein vorher nicht existierender Branch wird mit leerem Erwartungswert abgesichert. Ein Lease schützt gegen zwischenzeitliche Remote-Änderungen, nicht gegen das bewusst bestätigte Verwerfen bereits bekannter Remote-Commits.

Ein bestehender anderer lokaler Zielbranch wird nicht automatisch zurückgesetzt oder ausgecheckt. Zuerst bewusst mit Git auf ihn wechseln. Ein noch nicht existierender Branch kann vom aktuellen Stand neu angelegt werden. Detached HEAD und laufende Merge-/Rebase-/Cherry-Pick-Vorgänge werden blockiert.

Bestehende Remote-Konfigurationen werden nicht verändert. Das Tool setzt keine globale `safe.directory`-Ausnahme. Bei Git-Ownership-Fehlern den Ordner prüfen und nur einen bewusst vertrauenswürdigen konkreten Pfad außerhalb des Tools freigeben; keine pauschale Wildcard verwenden.

### Tags und Wiederholung

Tags werden separat gepusht. Ein vorhandener Tag ist nur akzeptabel, wenn er auf den erwarteten Commit zeigt. Abweichende Tags werden nicht ersetzt.

Nach erfolgreichem Branch-Push und fehlgeschlagenem Tag-Push ist „Nur Tag-Push erneut versuchen“ verfügbar. Dieser Retry ist an das bestätigte Projekt, den Branch und den Commit gebunden. Ein vorhandener Remote-Tag kann auch direkt über „Release für vorhandenen Tag öffnen“ geprüft werden.

### Releases

Die Release-Ansicht besitzt Tabs für Release Notes, Dateien und Ergebnisse:

1. API-Anmeldung auswählen bzw. Token eingeben.
2. Optional vorhandenes Release laden.
3. Titel und Notes bearbeiten; bei Bedarf Notes aus einer Datei laden oder generieren.
4. Vorschau prüfen.
5. Für GitHub optional Draft und Pre-Release aktivieren.
6. Dateien können bereits ausgewählt und vorbereitet werden, bevor das Release gespeichert wird.
7. Release erstellen oder mit ausdrücklich aktivierter Aktualisierung aktualisieren.
8. Dateien anschließend separat hochladen.
9. Einzelstatus prüfen und den Release-Link nach Bestätigung im Browser öffnen.

GitHub verwendet `body`; automatisch generierte Notes werden über den Generate-Notes-Endpunkt in den Editor geladen. GitLab verwendet `description`; generierte Notes basieren auf einem Commit-Vergleich zu einem eingegebenen vorherigen Tag. Das ist kein vollständiger Merge-Request-Changelog-Generator. GitLab-Draft-/Pre-Release-Schalter sind in diesem Workflow deaktiviert, nicht stillschweigend ignoriert.

Das Release wird nur an einen vorhandenen geprüften Tag gebunden. Git-, Tag-, Release- und Datei-Schreibvorgänge sind keine gemeinsame atomare Transaktion. Eine parallele Änderung des Remote-Tags nach Prüfung kann nicht vollständig ausgeschlossen werden; geschützte Tags im Anbieter nutzen.

## Anmeldung und Sicherheit

### Git

Die Anwendung verwendet die lokale Git-Installation, deren Credential Manager oder SSH-Konfiguration. Interaktive Terminal-Prompts sind deaktiviert, damit Hintergrundjobs nicht unbemerkt hängen. Vorher außerhalb der Anwendung anmelden und SSH-Hostschlüssel prüfen. Private SSH-Schlüssel werden nicht vom Tool gespeichert oder übertragen.

Git-Aufrufe verwenden Argumentlisten und `shell=False`. Git-Hooks und ausdrücklich konfigurierte SSH-/Credential-Helfer können trotzdem Programme ausführen. Nur vertrauenswürdige Projekte und Konfigurationen öffnen.

### API

- GitHub: Token-Eingabe, `GH_TOKEN`, `GITHUB_TOKEN` oder vorhandene Anmeldung über `gh auth token`.
- GitLab: Token-Eingabe, `GITLAB_TOKEN` oder `GLAB_TOKEN`.
- GitLab CLI wird nicht direkt aufgerufen; die Umsetzung nutzt die HTTP-API.

Git-Anmeldung und API-Anmeldung sind ausdrücklich getrennt. Ein Token muss Rechte für die jeweils verwendeten Release-/Package-Operationen besitzen. Bei GitHub typischerweise passende Repository-Contents-Schreibrechte; bei GitLab passende projektbezogene API-/Package-Berechtigungen. Mit minimalen Rechten beginnen und die Dokumentation des eigenen Anbieterstands prüfen.

Tokens werden nicht in Klartextdateien, Repository-URLs oder Logs geschrieben. Token-Felder sind verdeckt; API-Antworttexte bei Fehlern werden nicht ungefiltert ausgegeben. API-Verbindungen sind auf freigegebene HTTPS-Hosts beschränkt. Weiterleitungen werden nicht automatisch verfolgt, um Zugangsdaten nicht an unerwartete Ziele weiterzugeben. Speicherlöschung im Sinne garantiert überschriebenen RAMs bietet Python nicht; das Leeren des Feldes ist keine solche Garantie.

HTTPS-Zertifikatsprüfung bleibt aktiviert. Die HTTP-Schicht übernimmt aus Sicherheitsgründen weder `.netrc` noch implizite Umgebungs-Proxys. Unternehmens-Proxys und interne CA-Zertifikate benötigen daher eine bewusst geprüfte Erweiterung der Session-Konfiguration. Keine Empfehlung, TLS-Prüfung abzuschalten.

Die Web-Origin muss eine HTTPS-Origin ohne Pfad sein. Self-hosted GitLab und GitHub Enterprise sind vorgesehen, aber noch nicht live getestet. Unterpfad-Installationen und abweichende Enterprise-Upload-Hosts sind nicht allgemein abgedeckt. Unbekannte Upload-Hosts werden blockiert, statt ihnen automatisch Tokens zu senden.

## Datei-Uploads

### Unterstützt

- Mehrere beliebige reguläre Dateien: z. B. EXE, MSI, ZIP, TXT oder Prüfsummendateien.
- Auswahl hinzufügen und lokal wieder entfernen.
- Dateinamen, Größen und Einzelstatus.
- Upload-Fortschritt, Abbruchanforderung und erneuter Versuch.
- Erkennung gleichnamiger Assets.
- Optional ein ZIP und `SHA256SUMS.txt` aus der ausgewählten Dateiliste erzeugen.
- GitLab: zusätzliche bestehende HTTPS-Datei als Asset-Link verknüpfen.

Für vorhersehbare Namen über beide Plattformen werden konservative Dateinamen verlangt: ASCII-Buchstaben/Ziffern am Anfang, anschließend Buchstaben, Ziffern, Punkt, Bindestrich oder Unterstrich; kein abschließender Punkt. Dateien mit Leerzeichen/Umlauten müssen vor Auswahl umbenannt werden. Dateiinhalte werden dadurch nicht verändert. Symbolische Links sind nicht als Upload-Quelle zugelassen.

### GitHub

Uploads gehen an den Release-Asset-Endpunkt. Ein bereits vorhandenes Asset wird nur bei passender SHA-256 und bestätigtem Upload-Status als identisch behandelt. Fehlt ein verlässlicher Digest oder ist der Inhalt anders, wird nicht automatisch überschrieben. Auch unvollständige vorhandene Assets werden nicht automatisch gelöscht: bewusst auf GitHub entfernen oder einen anderen Dateinamen wählen.

### GitLab

Dateien werden in der **Generic Package Registry** abgelegt und über Release-Asset-Links verknüpft. Die Package-Version ist aus dem Tag abgeleitet; der Dateiname enthält SHA-256 und den Originalnamen. Beim Wiederholen werden vorhandene Package-Dateien und Checksummen geprüft. So kann nach einem gescheiterten Link-Schritt nur der fehlende Link ergänzt werden.

Package Registry muss verfügbar sein. Ein neu bestätigter Upload wird über den Server-Erfolg anerkannt; vorhandene Dateien werden über die Package-Metadaten geprüft. Die Lösung führt nicht nach jedem Upload einen vollständigen Download als End-to-End-Verifikation aus. Release-Links privater Projekte machen die dahinterliegenden Packages nicht öffentlich. Registry-Dateien können bestehen bleiben, wenn Link-Erstellung oder Abbruch danach erfolgt; sie müssen bei Bedarf bewusst im Anbieter aufgeräumt werden.

### Abbruch, Fortschritt und Teilerfolg

Dateien werden blockweise übertragen, nicht vollständig in RAM geladen. Für konsistente Wiederholungen wird jede Quelldatei vor dem Upload in eine temporäre Datei kopiert und gehasht. Das benötigt freien lokalen Speicher mindestens für das aktuelle Asset. Während des Kopierens sollte die Quelldatei nicht parallel gebaut oder verändert werden.

Der Fortschrittsbalken zeigt an den HTTP-Stream übergebene Bytes, nicht garantiert vom Server dauerhaft gespeicherte Bytes. Erfolg wird erst nach Serverantwort gemeldet. Ein Abbruch kann bis zum nächsten Block bzw. zum Netzwerk-Timeout dauern; bereits abgeschlossene Veröffentlichungen werden nicht zurückgerollt.

Es gibt keine automatische aggressive Wiederholung nicht-idempotenter Schreibanfragen. Bei unklarem Netzwerk-Ausgang zunächst Release/Assets prüfen und dann manuell erneut versuchen. Erfolgreiche Dateien werden bei passendem Remote-Nachweis erkannt, abweichende Inhalte blockiert. Dateien aus der Auswahl zu entfernen löscht keine bereits veröffentlichten Remote-Assets.

## Markdown und Oberfläche

Ein gemeinsamer Editor bietet Bearbeiten/Vorschau, Laden, Speichern und Erkennung ungespeicherter Änderungen. Unterstützt sind Überschriften, Hervorhebungen, Listen, Codeblöcke, Zitate, Links, Tabellen, Inline-Code und Trennlinien.

Speichern erfolgt über eine temporäre Datei mit anschließendem Austausch. Externe Dateiänderungen lösen eine zusätzliche Bestätigung aus. README wird beim Öffnen des Editors automatisch gesucht; ohne vorhandene README wird ein neuer bearbeitbarer Anfang angelegt. Eine geänderte README wird beim folgenden `git add -A` mit erfasst.

HTML aus Markdown wird nicht ausgeführt. Bilder und sonstige Ressourcen werden nicht nachgeladen; damit werden lokale Dateiabrufe und Tracking-Pixel verhindert. Externe Links benötigen eine Bestätigung und HTTPS. Die Qt-Vorschau ist keine pixelgenaue GitHub-Webansicht. Markdown-Dateien sind beim Laden auf UTF-8 und 5 MB begrenzt.

Visuelle Richtung: kühles Schieferblau, helle Panels, kobaltblaue Hauptaktionen, separate Statusbereiche und optional dunkle Darstellung. Die charakteristische Struktur bildet die tatsächlichen getrennten Schritte Projekt → Commit → Tag → Release → Dateien ab. Native Aktionssymbole, beschriftete Schaltflächen, Tastaturfokus und scrollbare Formulare unterstützen kleine Fenster. Die Layouts sind für 420 × 540 und größere Fenster ausgelegt; praktische Kontrolle bei verschiedenen Windows-Skalierungen steht noch aus.

## Testnachweis

Ausgeführt:

```text
python -m compileall -q .
python -m unittest discover -s tests -v

Ran 39 tests
OK (skipped=3)
```

36 bestandene Tests umfassen insbesondere:

- Initialisierung und Ablehnung verschachtelter Projektordner.
- Branch-/Tag-Push, Wiederholung ohne neue Änderungen.
- Sicheren Stopp bei Divergenz, Merge und explizites Force-with-lease.
- Simulierten konkurrierenden Remote-Push während des Lease-Pushs mit echten Git-Repositories.
- Schutz vorhandener lokaler Branches und Teilerfolg bei Tag-Konflikten.
- Ungültige Ref-Namen, URL-Prüfung und Redaktion.
- HTTP-Statusfehler, Host-Bindung und Abbruch vor HTTP-Anfragen.
- GitHub-Release-Payloads, Update-Freigabe und Asset-Kollisionen.
- GitLab-Release-Payloads, Notes, Link-Kollisionen und Wiederholung nach fehlgeschlagener Verknüpfung.
- ZIP, SHA-256, doppelte Dateien, Teilfehler und Abbruchstatus.
- Markdown-Rendering ohne ausführbares HTML oder nachgeladene Bilder.

Die drei mitgelieferten Qt-Smoke-Tests für Hauptfenster, Release-Dialoge und Editor werden bei verfügbarer PySide6-Installation ausgeführt. Hier wurden sie explizit übersprungen. Das vollständige lokale Testprotokoll liegt im Paket unter `TEST_RESULTS.txt`.

## Abnahme vor produktiver Nutzung

### Windows und Oberfläche

- [ ] Installation in frischer Python-3.12-x64-Umgebung; `pip check` erfolgreich.
- [ ] Alle 39 Tests erfolgreich; keine GUI-Skips auf der Build-Maschine.
- [ ] Start aus Python, über `start.bat` und aus gebauter EXE.
- [ ] Kleine Fenster, maximierte Fenster und 100/150/200-%-Skalierung.
- [ ] Tastaturnavigation, Fokus, Hell/Dunkel und lange Texte.
- [ ] Lokale Pfade, Leerzeichen, Umlaute, Netzlaufwerke und UNC-Pfade.
- [ ] README/Notes laden, bearbeiten, Vorschau, Speichern, externe Änderung und Abbruch beim Schließen.

### Git und Anbieter

- [ ] GitHub und GitLab jeweils mit HTTPS und SSH gegen ausschließlich entbehrliche Test-Repositories.
- [ ] Credential Manager/SSH-Agent; fehlende Anmeldung und verweigerte Rechte.
- [ ] Bestehender Branch, neuer Branch, neue lokale Initialisierung und geschützte Branches.
- [ ] Divergenz, unabhängige Historien und echte Merge-Konflikte.
- [ ] GitHub Draft/Pre-Release sowie GitLab-Release, vorhandenes Release und Update.
- [ ] Generierte Notes und nachträgliche manuelle Bearbeitung.
- [ ] Private Asset-Downloads und tatsächlich benötigte Token-Rechte.

### Upload und Verteilung

- [ ] Kleine, große und leere Datei; mehrere Dateien; Dateinamenskonflikte.
- [ ] Abbruch beim Kopieren, Hashen, Übertragen und nach Serverantwort.
- [ ] Verbindungsunterbrechung, Rate-Limit und verweigerte Registry-Rechte.
- [ ] Retry ohne doppelte Veröffentlichung; sichtbare Teilergebnisse.
- [ ] SHA-256 nach echtem Download vergleichen.
- [ ] EXE auf sauberem Windows-System mit Git, aber ohne Python starten.
- [ ] Abhängigkeits-/Lizenzprüfung, Codesignierung und dokumentierte Freigabe.

## Referenzen

- [Repository und Bestandsquellen](https://github.com/NKAutomations/git-push-tool)
- [GitHub Releases API](https://docs.github.com/en/rest/releases/releases?apiVersion=2022-11-28)
- [GitHub Release Assets API](https://docs.github.com/en/rest/releases/assets?apiVersion=2022-11-28)
- [GitHub CLI – auth token](https://cli.github.com/manual/gh_auth_token)
- [GitLab Releases API](https://docs.gitlab.com/api/releases/)
- [GitLab Generic Packages](https://docs.gitlab.com/user/packages/generic_packages/)
