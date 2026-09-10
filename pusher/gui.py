"""Desktop views. Workers receive immutable snapshots, never Qt widgets."""
import sys
import tempfile
from pathlib import Path
from PySide6.QtCore import Qt, QUrl, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QGroupBox, QScrollArea, QLabel, QLineEdit, QPushButton,
    QComboBox, QCheckBox, QPlainTextEdit, QTabWidget, QFileDialog, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QProgressBar, QStyle)
from .models import AppError, Report, ReleaseOptions, PushOptions, checkpoint
from .security import Repository, redact, https_url
from .git_service import GitService
from .http_client import HttpClient
from .providers import provider_for
from .auth import resolve_token
from .assets import validate_files, prepare, upload_files
from .editor import MarkdownEditor, ReadmeDialog
from .jobs import Job
from .theme import stylesheet


STATUS = {'success': 'Erfolgreich', 'failed': 'Fehler', 'cancelled': 'Abgebrochen',
          'blocked': 'Nicht ausgeführt', 'skipped': 'Übersprungen'}


def button(text, callback, primary=False):
    widget = QPushButton(text)
    if primary:
        widget.setObjectName('primary')
    if primary:
        widget.setIcon(widget.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp))
    elif text.startswith(('Datei', 'Projektordner', 'README')):
        widget.setIcon(widget.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
    elif 'abbrechen' in text.lower():
        widget.setIcon(widget.style().standardIcon(QStyle.StandardPixmap.SP_DialogCancelButton))
    widget.clicked.connect(callback)
    return widget


def label(text, object_name=''):
    widget = QLabel(text)
    widget.setWordWrap(True)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    if object_name:
        widget.setObjectName(object_name)
    return widget


def form_group(title):
    group = QGroupBox(title)
    form = QFormLayout(group)
    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    return group, form


def scroll(content):
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(content)
    return area


def report_text(report):
    return '\n\n'.join(f'{step.stage} · {STATUS.get(step.status, step.status)}\n{step.message}'
                       + (f'\n{step.url}' if step.url else '') for step in report.steps)


def open_https(parent, url):
    try:
        https_url(url)
    except AppError as error:
        QMessageBox.warning(parent, 'Link nicht geöffnet', str(error))
        return
    if QMessageBox.question(parent, 'Im Browser öffnen', url) == QMessageBox.StandardButton.Yes:
        QDesktopServices.openUrl(QUrl(url))


class TaskView:
    """A single worker per view. Closing while a worker is alive is prevented."""
    def setup_tasks(self, root):
        self.job = None
        self.callback = None
        self.busy_label = label('Bereit')
        self.progressbar = QProgressBar()
        self.progressbar.setRange(0, 100)
        self.cancel_button = button('Vorgang abbrechen', self.cancel_task)
        self.cancel_button.setEnabled(False)
        root.addWidget(self.busy_label)
        root.addWidget(self.progressbar)
        root.addWidget(self.cancel_button)

    def start_task(self, title, function, callback):
        if self.job is not None:
            return
        self.callback = callback
        self.controls.setEnabled(False)
        self.busy_label.setText(title)
        self.progressbar.setRange(0, 0)
        self.cancel_button.setEnabled(True)
        self.job = Job(function, self)
        self.job.succeeded.connect(self.task_success)
        self.job.failed.connect(self.task_error)
        self.job.progress.connect(self.task_progress)
        self.job.log.connect(self.log_message)
        self.job.finished.connect(self.task_finished)
        self.job.start()

    @Slot(str)
    def log_message(self, text):
        if '\t' in text and hasattr(self, 'asset_status'):
            self.asset_status(text)
        else:
            self.results.appendPlainText(redact(text))

    @Slot(object)
    def task_success(self, result):
        try:
            self.callback(result)
        except Exception:
            self.task_error('Ergebnis konnte nicht angezeigt werden. Vor Wiederholung den Remote-Stand prüfen.')

    @Slot(str)
    def task_error(self, message):
        self.busy_label.setText(message)
        self.results.appendPlainText('\nFehler: ' + message)
        QMessageBox.warning(self, 'Vorgang nicht abgeschlossen', message)

    @Slot(str, object, object)
    def task_progress(self, name, sent, total):
        self.progressbar.setRange(0, 100)
        self.progressbar.setValue(int(sent * 100 / total) if total else 0)
        self.busy_label.setText(f'{name}: {sent:,} / {total:,} Bytes übertragen — Serverbestätigung folgt')

    @Slot()
    def task_finished(self):
        worker = self.job
        self.job = None
        self.callback = None
        self.controls.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progressbar.setRange(0, 100)
        self.progressbar.setValue(0)
        if worker:
            worker.deleteLater()

    def cancel_task(self):
        if self.job:
            self.job.cancel.set()
            self.busy_label.setText('Abbruch angefordert. Laufende Netzwerkanfrage kann bis zum Zeitlimit weiterlaufen.')
            self.cancel_button.setEnabled(False)

    def can_close(self):
        if self.job:
            self.cancel_task()
            QMessageBox.information(self, 'Vorgang läuft', 'Abbruch ist angefordert. Nach Ende des Vorgangs erneut schließen. Bereits veröffentlichte Daten bleiben erhalten.')
            return False
        return True


class ReleaseDialog(QDialog, TaskView):
    def __init__(self, repository, project, tag, commit, parent=None):
        super().__init__(parent)
        self.repository, self.project = repository, project
        self.tag, self.commit = tag, commit
        self.release = None
        self.paths = []
        self.temp = tempfile.TemporaryDirectory(prefix='pusher-generated-')
        self.setWindowTitle('Release und Dateien')
        self.resize(960, 780)
        self.setMinimumSize(420, 540)
        root = QVBoxLayout(self)
        root.addWidget(label('Release vorbereiten', 'title'))
        root.addWidget(label(f'{repository.provider} · {repository.project}\nTag {tag} · Commit {commit[:12]}', 'subtitle'))
        self.controls = QTabWidget()
        root.addWidget(self.controls, 1)
        notes_page = QWidget()
        notes_layout = QVBoxLayout(notes_page)
        group, form = form_group('API-Anmeldung — getrennt von Git')
        self.token = QLineEdit()
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.token.setPlaceholderText('Nur im Arbeitsspeicher; alternativ Umgebungsvariable')
        self.source = QComboBox()
        self.source.addItem('Token-Feld / Umgebungsvariable', 'environment')
        if repository.provider == 'GitHub':
            self.source.addItem('GitHub CLI: gh auth token', 'gh')
        form.addRow('API-Token', self.token)
        form.addRow('Anmeldequelle', self.source)
        form.addRow(label(f'Token wird ausschließlich an {repository.api_origin} gesendet' + (' sowie uploads.github.com.' if repository.web_origin == 'https://github.com' else '.')))
        notes_layout.addWidget(group)
        group, form = form_group('Release-Metadaten')
        self.title = QLineEdit(tag)
        self.update = QCheckBox('Vorhandenes Release aktualisieren')
        self.draft = QCheckBox('Entwurf (Draft)')
        self.prerelease = QCheckBox('Vorabversion (Pre-Release)')
        for widget in (self.draft, self.prerelease):
            widget.setEnabled(repository.provider == 'GitHub')
            if repository.provider != 'GitHub':
                widget.setToolTip('Nur GitHub unterstützt diese Optionen in diesem Workflow.')
        self.previous = QLineEdit()
        self.previous.setPlaceholderText('z. B. v1.0.0; für GitLab erforderlich')
        form.addRow('Titel', self.title)
        form.addRow(self.update)
        form.addRow(self.draft)
        form.addRow(self.prerelease)
        form.addRow('Vorheriger Tag', self.previous)
        form.addRow(button('Vorhandenes Release laden', self.load_release))
        form.addRow(button('Release Notes generieren', self.generate_notes))
        notes_layout.addWidget(group)
        self.editor = MarkdownEditor()
        self.editor.setMinimumHeight(300)
        notes_layout.addWidget(self.editor, 1)
        notes_layout.addWidget(button('Release erstellen / aktualisieren', self.publish, True))
        self.controls.addTab(scroll(notes_page), 'Release Notes')
        files_page = QWidget()
        files_layout = QVBoxLayout(files_page)
        files_layout.addWidget(label('Dateien werden separat hochgeladen. Bei einem Fehler bleibt das Release erhalten. Erfolgreiche Dateien werden bei Wiederholung sicher erkannt.'))
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(['Dateiname', 'Größe', 'Status'])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setMinimumHeight(180)
        files_layout.addWidget(self.table)
        for text, callback in [('Dateien hinzufügen', self.add_files), ('Auswahl entfernen', self.remove_files),
                               ('ZIP + SHA-256 erzeugen', self.generate_bundle), ('Vorhandene Assets prüfen', self.inspect_assets),
                               ('Dateien hochladen / erneut versuchen', self.upload)]:
            files_layout.addWidget(button(text, callback, text.startswith('Dateien hochladen')))
        if repository.provider == 'GitLab':
            group, form = form_group('Optional: vorhandene HTTPS-Datei verlinken')
            self.link_name, self.link_url = QLineEdit(), QLineEdit()
            form.addRow('Anzeigename', self.link_name)
            form.addRow('HTTPS-URL', self.link_url)
            form.addRow(button('Asset-Link hinzufügen', self.add_link))
            files_layout.addWidget(group)
        files_layout.addStretch()
        self.controls.addTab(scroll(files_page), 'Dateien')
        result_page = QWidget()
        result_layout = QVBoxLayout(result_page)
        self.results = QPlainTextEdit()
        self.results.setReadOnly(True)
        result_layout.addWidget(self.results)
        result_layout.addWidget(button('Release im Browser öffnen', self.open_release))
        self.controls.addTab(result_page, 'Ergebnisse')
        self.setup_tasks(root)

    def with_provider(self, operation):
        explicit, source = self.token.text(), self.source.currentData()
        repo = self.repository
        def run(job):
            checkpoint(job.cancel)
            token = resolve_token(repo, explicit, source)
            client = HttpClient(repo, token, cancel=job.cancel)
            try:
                return operation(provider_for(repo, client), job)
            finally:
                client.close()
        return run

    def verify(self, job):
        GitService(self.project, job.cancel).verify_tag(self.repository.clone, self.tag, self.commit)

    def load_release(self):
        if not self.editor.confirm_discard():
            return
        def operation(provider, job):
            self.verify(job)
            release = provider.find(self.tag)
            if not release:
                raise AppError('release_missing', 'Für diesen Tag gibt es noch kein sichtbares Release.')
            return release
        self.start_task('Release wird geladen …', self.with_provider(operation), self.loaded)

    def loaded(self, release):
        self.release = release
        self.title.setText(release.title)
        self.editor.path = None
        self.editor.disk_baseline = None
        self.editor.set_text(release.notes, clean=True)
        self.draft.setChecked(release.draft)
        self.prerelease.setChecked(release.prerelease)
        self.update.setChecked(True)
        self.results.appendPlainText('Release geladen: ' + release.url)
        self.busy_label.setText('Release geladen. Änderungen vor dem Aktualisieren prüfen.')

    def generate_notes(self):
        if not self.editor.confirm_discard():
            return
        previous = self.previous.text().strip()
        def operation(provider, job):
            self.verify(job)
            return provider.generate_notes(self.tag, previous)
        self.start_task('Release Notes werden generiert …', self.with_provider(operation), self.notes_generated)

    def notes_generated(self, text):
        self.editor.set_text(text)
        self.busy_label.setText('Notes generiert. Vor dem Veröffentlichen bearbeiten und Vorschau prüfen.')

    def publish(self):
        title = self.title.text().strip()
        if not title:
            QMessageBox.warning(self, 'Titel fehlt', 'Einen Release-Titel eingeben.')
            return
        options = ReleaseOptions(self.tag, title, self.editor.text.toPlainText(), self.update.isChecked(),
                                 self.draft.isChecked(), self.prerelease.isChecked())
        action = 'aktualisieren' if options.update else 'erstellen'
        if QMessageBox.question(self, 'Release bestätigen', f'Release {self.tag} auf {self.repository.web_origin} {action}?\nDateien werden danach separat hochgeladen.') != QMessageBox.StandardButton.Yes:
            return
        def operation(provider, job):
            self.verify(job)
            return provider.publish(options)
        self.start_task('Release wird gespeichert …', self.with_provider(operation), self.published)

    def published(self, release):
        self.release = release
        self.update.setChecked(True)
        report = Report()
        report.add('Release', 'success', 'Release gespeichert; Datei-Uploads sind ein separater Schritt.', release.url)
        self.results.appendPlainText(report_text(report))
        self.busy_label.setText('Release erfolgreich gespeichert. Dateien im Tab „Dateien“ hochladen.')
        # Publishing does not imply saving the local notes file; dirty state is preserved.
        self.controls.setCurrentIndex(1 if self.paths else 2)

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, 'Release-Dateien auswählen', '', 'Alle Dateien (*)')
        if not paths:
            return
        try:
            self.paths = validate_files([*self.paths, *map(Path, paths)])
            self.refresh_files()
        except (AppError, OSError) as error:
            QMessageBox.warning(self, 'Dateiauswahl prüfen', redact(str(error)))

    def refresh_files(self):
        self.table.setRowCount(len(self.paths))
        for row, path in enumerate(self.paths):
            size = f'{path.stat().st_size:,} Bytes' if path.exists() else 'Nicht mehr vorhanden'
            for col, text in enumerate((path.name, size, 'Bereit')):
                self.table.setItem(row, col, QTableWidgetItem(text))
            self.table.item(row, 0).setToolTip(str(path))

    def remove_files(self):
        selected = {index.row() for index in self.table.selectionModel().selectedRows()}
        self.paths = [path for row, path in enumerate(self.paths) if row not in selected]
        self.refresh_files()

    def generate_bundle(self):
        if not self.paths:
            QMessageBox.information(self, 'Keine Dateien', 'Zuerst Dateien hinzufügen.')
            return
        folder = QFileDialog.getExistingDirectory(self, 'Neuen Unterordner für ZIP und Prüfsummen hier anlegen')
        if not folder:
            return
        paths = list(self.paths)
        # A fresh directory prevents accidental overwrites of previous bundles.
        def operation(job):
            output = tempfile.mkdtemp(prefix='release-', dir=folder)
            return prepare(paths, output, True, True, job.cancel)
        self.start_task('ZIP und Prüfsummen werden erzeugt …', operation, self.bundle_ready)

    def bundle_ready(self, paths):
        self.paths = paths
        self.refresh_files()
        self.busy_label.setText('ZIP und Prüfsummen erzeugt und zur Upload-Liste hinzugefügt.')

    def require_release(self):
        if not self.release:
            QMessageBox.information(self, 'Release fehlt', 'Zuerst ein Release erstellen oder ein vorhandenes Release laden.')
            return False
        return True

    def inspect_assets(self):
        if not self.require_release():
            return
        release = self.release
        self.start_task('Vorhandene Assets werden gelesen …', self.with_provider(lambda provider, job: provider.assets(release)), self.assets_loaded)

    def assets_loaded(self, assets):
        self.results.appendPlainText('Vorhandene Assets:\n' + ('\n'.join(f'{a.name} · {a.size if a.size else "Größe nicht gemeldet"}\n{a.url}' for a in assets) or 'Keine Assets.'))
        names = {a.name.casefold() for a in assets}
        for row, path in enumerate(self.paths):
            if path.name.casefold() in names:
                self.table.setItem(row, 2, QTableWidgetItem('Vorhanden; Inhalt wird beim Upload geprüft'))
        self.busy_label.setText(f'{len(assets)} vorhandene Assets erkannt.')
        self.controls.setCurrentIndex(2)

    def upload(self):
        if not self.require_release():
            return
        if not self.paths:
            QMessageBox.information(self, 'Keine Dateien', 'Zuerst Dateien hinzufügen.')
            return
        if QMessageBox.question(self, 'Dateien hochladen', f'{len(self.paths)} Dateien an Release {self.tag} anhängen?\nVorhandene abweichende Dateien werden nicht überschrieben.') != QMessageBox.StandardButton.Yes:
            return
        paths, release = list(self.paths), self.release
        def operation(provider, job):
            self.verify(job)
            return upload_files(provider, release, paths, job.cancel, job.progress.emit, job.log.emit)
        self.start_task('Dateien werden geprüft und hochgeladen …', self.with_provider(operation), self.uploaded)

    @Slot(str)
    def asset_status(self, text):
        name, _, status = text.partition('\t')
        for row, path in enumerate(self.paths):
            if path.name == name:
                self.table.setItem(row, 2, QTableWidgetItem(status))

    def uploaded(self, report):
        self.results.appendPlainText(report_text(report))
        by_name = {s.stage: s for s in report.steps}
        for row, path in enumerate(self.paths):
            if path.name in by_name:
                step = by_name[path.name]
                self.table.setItem(row, 2, QTableWidgetItem(STATUS.get(step.status, step.status)))
                self.table.item(row, 2).setToolTip(step.message)
        self.busy_label.setText('Upload abgeschlossen.' if report.outcome == 'success' else 'Upload nur teilweise oder nicht abgeschlossen. Einzelstatus prüfen; fehlgeschlagene Dateien erneut versuchen.')
        self.controls.setCurrentIndex(2)

    def add_link(self):
        if not self.require_release():
            return
        name, url, release = self.link_name.text().strip(), self.link_url.text().strip(), self.release
        try:
            https_url(url)
            if not name:
                raise AppError('name', 'Asset-Anzeigename eingeben.')
        except AppError as error:
            QMessageBox.warning(self, 'Link prüfen', str(error))
            return
        if QMessageBox.question(self, 'Link veröffentlichen', f'{name}\n{url}\nAls Release-Asset hinzufügen?') != QMessageBox.StandardButton.Yes:
            return
        self.start_task('Asset-Link wird angelegt …', self.with_provider(lambda provider, job: provider.add_link(release, name, url)), self.link_added)

    def link_added(self, asset):
        self.results.appendPlainText(f'Asset-Link erstellt: {asset.name}\n{asset.url}')
        self.busy_label.setText('Asset-Link erstellt.')

    def open_release(self):
        if self.require_release():
            open_https(self, self.release.url)

    def reject(self):
        if self.can_close() and self.editor.confirm_discard():
            self.token.clear()
            self.temp.cleanup()
            super().reject()

    def closeEvent(self, event):
        if self.can_close() and self.editor.confirm_discard():
            self.token.clear()
            self.temp.cleanup()
            event.accept()
        else:
            event.ignore()


class MainWindow(QMainWindow, TaskView):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Git Repository Pusher')
        self.resize(1000, 840)
        self.setMinimumSize(420, 540)
        self.last_push = None
        self.last_tag_context = None
        central = QWidget()
        root = QVBoxLayout(central)
        root.addWidget(label('Vom Projekt zum Release.', 'title'))
        root.addWidget(label('Git Repository Pusher · GitHub & GitLab', 'subtitle'))
        self.dark = QCheckBox('Dunkle Darstellung')
        self.dark.toggled.connect(lambda value: QApplication.instance().setStyleSheet(stylesheet(value)))
        root.addWidget(self.dark)
        self.controls = QTabWidget()
        root.addWidget(self.controls, 1)
        page = QWidget()
        layout = QVBoxLayout(page)
        group, form = form_group('Projekt und Repository')
        self.project = QLineEdit()
        form.addRow('Projektordner', self.project)
        form.addRow(button('Projektordner auswählen', self.choose_project))
        self.provider = QComboBox()
        self.provider.addItems(['GitHub', 'GitLab'])
        self.remote = QLineEdit()
        self.remote.setPlaceholderText('https://github.com/owner/repo.git oder git@host:gruppe/projekt.git')
        self.origin = QLineEdit()
        self.origin.setPlaceholderText('Optional: https://git.example.org für abweichenden SSH-Host')
        self.branch = QLineEdit('main')
        form.addRow('Plattform', self.provider)
        form.addRow('Repository-URL', self.remote)
        form.addRow('Web-Origin', self.origin)
        form.addRow('Ziel-Branch', self.branch)
        form.addRow(label('Git nutzt den eingerichteten Credential Manager oder SSH-Agenten. Keine Tokens in Repository-URLs eingeben. Bestehende Remotes werden nicht geändert.'))
        form.addRow(button('Verbindung prüfen', self.connection))
        form.addRow(button('README öffnen / anlegen', self.readme))
        layout.addWidget(group)
        group, form = form_group('Änderungen und Commit')
        self.message = QLineEdit()
        self.message.setPlaceholderText('Was wurde geändert?')
        self.mode = QComboBox()
        self.mode.addItem('Sicher stoppen bei zusätzlicher Remote-Historie', 'safe')
        self.mode.addItem('Remote-Historie integrieren (Merge)', 'integrate')
        self.mode.addItem('Remote ersetzen — explizites Force-with-lease', 'replace')
        self.unrelated = QCheckBox('Beim Merge auch unabhängige Historien erlauben')
        self.unrelated.setEnabled(False)
        self.mode.currentIndexChanged.connect(lambda _: self.unrelated.setEnabled(self.mode.currentData() == 'integrate'))
        form.addRow('Commit-Nachricht', self.message)
        form.addRow('Remote-Historie', self.mode)
        form.addRow(self.unrelated)
        form.addRow(button('Änderungen prüfen', self.review))
        form.addRow(label('Committen erfasst alle Änderungen mit git add -A, einschließlich neuer Dateien und Löschungen. Vorher .gitignore und vertrauliche Dateien prüfen. Git-Hooks des Projekts können ausgeführt werden; nur vertrauenswürdige Projekte öffnen.'))
        layout.addWidget(group)
        group, form = form_group('Optional: Tag und Release')
        self.tag = QLineEdit()
        self.tag.setPlaceholderText('z. B. v1.2.0; leer lassen für reinen Branch-Push')
        self.tag_message = QLineEdit()
        self.auto_release = QCheckBox('Nach erfolgreichem Tag-Push Release-Ansicht öffnen')
        form.addRow('Tag', self.tag)
        form.addRow('Tag-Nachricht', self.tag_message)
        form.addRow(self.auto_release)
        form.addRow(button('Committen und pushen', self.push, True))
        form.addRow(button('Nur Tag-Push erneut versuchen', self.retry_tag))
        self.open_last_release_button = button('Release des letzten erfolgreichen Tags öffnen', self.open_last_release)
        self.open_last_release_button.setEnabled(False)
        self.open_last_release_button.setToolTip('Wird nach einem erfolgreichen Tag-Push aktiviert.')
        form.addRow(self.open_last_release_button)
        form.addRow(button('Release für vorhandenen Tag öffnen', self.existing_release))
        layout.addWidget(group)
        layout.addStretch()
        self.controls.addTab(scroll(page), 'Projekt → Commit → Tag')
        self.results = QPlainTextEdit()
        self.results.setReadOnly(True)
        self.controls.addTab(self.results, 'Prüfung und Ergebnisse')
        self.setup_tasks(root)
        self.setCentralWidget(central)

    def context(self):
        project = Path(self.project.text().strip()).expanduser()
        if not self.project.text().strip() or not project.is_dir():
            raise AppError('project', 'Einen vorhandenen Projektordner auswählen.')
        repo = Repository.parse(self.remote.text().strip(), self.provider.currentText(), self.origin.text().strip())
        return project.resolve(), repo

    def guarded_context(self):
        try:
            return self.context()
        except AppError as error:
            QMessageBox.warning(self, 'Eingaben prüfen', str(error))
            return None

    def choose_project(self):
        folder = QFileDialog.getExistingDirectory(self, 'Projektordner auswählen', self.project.text())
        if folder:
            self.project.setText(folder)
            self.last_push = None
            self.last_tag_context = None
            self.open_last_release_button.setEnabled(False)

    def readme(self):
        project = Path(self.project.text().strip())
        if not self.project.text().strip() or not project.is_dir():
            QMessageBox.warning(self, 'Projekt fehlt', 'Zuerst einen vorhandenen Projektordner auswählen.')
            return
        try:
            dialog = ReadmeDialog(project.resolve(), self)
            dialog.exec()
            dialog.deleteLater()
        except OSError:
            QMessageBox.warning(self, 'README nicht verfügbar', 'Projektordner ist nicht lesbar.')

    def connection(self):
        context = self.guarded_context()
        if context:
            project, repo = context
            self.start_task('Git-Verbindung wird geprüft …', lambda job: GitService(project, job.cancel, job.log.emit).check_connection(repo.clone), self.text_result)

    def review(self):
        context = self.guarded_context()
        if context:
            project, repo = context
            branch = self.branch.text().strip()
            self.start_task('Änderungen werden geprüft …', lambda job: GitService(project, job.cancel).review(branch), self.text_result)

    def text_result(self, text):
        self.results.appendPlainText(redact(text))
        self.controls.setCurrentIndex(1)
        self.busy_label.setText('Prüfung abgeschlossen; Details im Ergebnisbereich.')

    def push(self):
        context = self.guarded_context()
        if not context:
            return
        project, repo = context
        options = PushOptions(project, repo.clone, self.branch.text().strip(), self.message.text(),
                              self.tag.text().strip(), self.tag_message.text(), self.mode.currentData(),
                              self.unrelated.isChecked() and self.mode.currentData() == 'integrate')
        if self.auto_release.isChecked() and not options.tag:
            QMessageBox.warning(self, 'Tag fehlt', 'Für ein Release einen Tag eingeben.')
            return
        warning = f'Alle Projektänderungen committen und Branch {options.branch} zu {repo.project} auf {repo.web_origin} pushen?\n\nGelöschte und neue Dateien werden einbezogen. Hooks können ausgeführt werden.'
        if options.mode == 'replace':
            warning += '\n\nACHTUNG: Remote-Commits dürfen ersetzt werden. Ein explizites Lease schützt nur vor Änderungen nach der Remote-Prüfung, nicht vor dem bewusst bestätigten Ersetzen.'
        if QMessageBox.question(self, 'Git-Push bestätigen', warning) != QMessageBox.StandardButton.Yes:
            return
        self.pending_context = (project, repo, options.branch)
        self.open_after_push = self.auto_release.isChecked()
        self.last_push = None
        self.start_task('Commit und Git-Push laufen …', lambda job: GitService(project, job.cancel, job.log.emit).push(options), self.pushed)

    def pushed(self, report):
        self.results.appendPlainText(report_text(report))
        self.controls.setCurrentIndex(1)
        self.busy_label.setText('Git-Ablauf abgeschlossen.' if report.outcome == 'success' else 'Git-Ablauf nicht vollständig abgeschlossen. Einzelstatus prüfen.')
        if report.commit:
            self.last_push = (*self.pending_context, report.commit)
        if report.tag and self.open_after_push:
            # Open only once QThread.finished has released the main view.
            self.next_release = (*self.pending_context[:2], report.tag, report.commit)
        if report.tag and report.outcome == 'success':
            self.last_tag_context = (*self.pending_context[:2], report.tag, report.commit)
            self.open_last_release_button.setEnabled(True)

    @Slot()
    def task_finished(self):
        TaskView.task_finished(self)
        pending = getattr(self, 'next_release', None)
        self.next_release = None
        if pending:
            self.show_release(pending)

    def retry_tag(self):
        if not self.last_push:
            QMessageBox.information(self, 'Kein bestätigter Branch-Push', 'Zuerst einen Branch erfolgreich pushen. Bereits vorhandene Remote-Tags können über die Release-Ansicht geöffnet werden.')
            return
        context = self.guarded_context()
        if not context:
            return
        project, repo, branch, commit = self.last_push
        if context != (project, repo) or self.branch.text().strip() != branch:
            QMessageBox.warning(self, 'Projekt geändert', 'Tag-Retry gilt nur für das zuletzt erfolgreich gepushte Projekt und den Branch.')
            return
        tag, message = self.tag.text().strip(), self.tag_message.text()
        if QMessageBox.question(self, 'Tag-Push bestätigen', f'Tag {tag} auf Commit {commit[:12]} erstellen und pushen?') != QMessageBox.StandardButton.Yes:
            return
        def operation(job):
            service = GitService(project, job.cancel)
            detail = service.push_tag(repo.clone, tag, message, commit)
            report = Report(commit=commit, tag=tag)
            report.add('Tag-Push', 'success', detail)
            return report
        self.pending_context = (project, repo, branch)
        self.open_after_push = self.auto_release.isChecked()
        self.start_task('Tag-Push wird wiederholt …', operation, self.pushed)

    def open_last_release(self):
        if not self.last_tag_context:
            QMessageBox.information(self, 'Kein erfolgreicher Tag-Push', 'Zuerst einen Tag erfolgreich pushen.')
            return
        self.show_release(self.last_tag_context)

    def existing_release(self):
        context = self.guarded_context()
        if not context:
            return
        project, repo = context
        tag = self.tag.text().strip()
        def operation(job):
            service = GitService(project, job.cancel)
            service.valid_ref(tag, 'tags')
            ref = f'refs/tags/{tag}'
            refs = service.remote_refs(repo.clone, ref)
            commit = refs.get(ref + '^{}', refs.get(ref))
            if not commit:
                raise AppError('tag_missing', 'Remote-Tag fehlt. Zuerst einen Tag pushen.')
            return project, repo, tag, commit
        self.start_task('Remote-Tag wird geprüft …', operation, self.release_context_ready)

    def release_context_ready(self, context):
        self.next_release = context
        self.busy_label.setText('Remote-Tag bestätigt.')

    def show_release(self, context):
        try:
            dialog = ReleaseDialog(*context, self)
        except Exception as error:
            self.results.appendPlainText('Release-Dialog konnte nicht geöffnet werden: ' + redact(str(error)))
            QMessageBox.critical(self, 'Release-Dialog nicht verfügbar',
                                 'Der Release-Dialog konnte nicht geöffnet werden.\n\n'
                                 + redact(str(error)))
            return
        dialog.setModal(True)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        self.release_dialog = dialog
        dialog.exec()
        self.release_dialog = None
        dialog.deleteLater()

    def closeEvent(self, event):
        event.accept() if self.can_close() else event.ignore()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('Git Repository Pusher')
    app.setOrganizationName('NKAutomations')
    app.setStyle('Fusion')
    app.setStyleSheet(stylesheet())
    window = MainWindow()
    window.show()
    return app.exec()
