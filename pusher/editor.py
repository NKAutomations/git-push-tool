import os
import tempfile
from pathlib import Path
from markdown_it import MarkdownIt
from PySide6.QtCore import QUrl, QTimer
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QTextBrowser,
                              QPushButton, QTabWidget, QLabel, QFileDialog, QMessageBox, QDialog)
from .security import https_url
from .models import AppError


def render_markdown(text):
    renderer = MarkdownIt('commonmark', {'html': False, 'linkify': False}).enable('table').enable('strikethrough')
    # Never fetch images, local files, or remote tracking pixels in preview.
    renderer.renderer.rules['image'] = lambda tokens, idx, options, env: '[Bild deaktiviert]'
    return renderer.render(text)


class SafePreview(QTextBrowser):
    def loadResource(self, kind, url):
        return None


class MarkdownEditor(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.render_timer = QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.setInterval(200)
        self.render_timer.timeout.connect(self.refresh)
        self.path = None
        self.baseline = ''
        self.disk_baseline = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        tools = QHBoxLayout()
        for label, callback in [('Datei laden', self.load_dialog), ('Speichern', self.save)]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            tools.addWidget(button)
        self.state = QLabel('Unveraendert')
        tools.addWidget(self.state)
        tools.addStretch()
        layout.addLayout(tools)
        self.tabs = QTabWidget()
        self.text = QPlainTextEdit()
        self.text.setAccessibleName('Markdown bearbeiten')
        self.text.setObjectName('markdownInput')
        self.preview = SafePreview()
        self.preview.setOpenLinks(False)
        self.preview.setOpenExternalLinks(False)
        self.preview.anchorClicked.connect(self.open_link)
        self.tabs.addTab(self.text, 'Bearbeiten')
        self.tabs.addTab(self.preview, 'Vorschau')
        self.tabs.currentChanged.connect(self.refresh)
        layout.addWidget(self.tabs)
        self.text.textChanged.connect(self.modified)
        self.shortcut = QShortcut(QKeySequence.StandardKey.Save, self)
        self.shortcut.activated.connect(self.save)

    @property
    def dirty(self):
        return self.text.toPlainText() != self.baseline

    def modified(self):
        self.state.setText('Ungespeicherte Aenderungen' if self.dirty else 'Unveraendert')
        if self.tabs.currentIndex() == 1:
            self.render_timer.start()

    def set_text(self, text, clean=False):
        if clean:
            self.baseline = text
        self.text.setPlainText(text)
        self.modified()
        self.refresh()

    def refresh(self, *_):
        if self.tabs.currentIndex() == 1:
            self.preview.setHtml(render_markdown(self.text.toPlainText()))

    def open_link(self, url):
        try:
            https_url(url.toString())
        except AppError:
            QMessageBox.warning(self, 'Link blockiert', 'Nur HTTPS-Links ohne Zugangsdaten sind erlaubt.')
            return
        if QMessageBox.question(self, 'Link oeffnen', url.toString()) == QMessageBox.StandardButton.Yes:
            QDesktopServices.openUrl(url)

    def confirm_discard(self):
        if not self.dirty:
            return True
        choice = QMessageBox.question(self, 'Ungespeicherter Text', 'Aenderungen vor dem Fortfahren speichern?',
                                      QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        if choice == QMessageBox.StandardButton.Save:
            return self.save()
        return choice == QMessageBox.StandardButton.Discard

    def load_dialog(self):
        if not self.confirm_discard():
            return
        name, _ = QFileDialog.getOpenFileName(self, 'Markdown laden', '', 'Markdown (*.md *.markdown *.txt);;Alle Dateien (*)')
        if name:
            self.load(Path(name))

    def load(self, path):
        try:
            if path.stat().st_size > 5_000_000:
                raise ValueError('Markdown-Datei ist groesser als 5 MB.')
            content = path.read_bytes()
            text = content.decode('utf-8-sig')
        except (OSError, UnicodeError, ValueError):
            QMessageBox.warning(self, 'Datei nicht geladen', 'Eine lesbare UTF-8-Datei bis 5 MB auswaehlen. Vorhandener Text bleibt erhalten.')
            return False
        self.path, self.disk_baseline = path, content
        self.set_text(text, clean=True)
        return True

    def save(self):
        path = self.path
        if path is None:
            name, _ = QFileDialog.getSaveFileName(self, 'Markdown speichern', 'release-notes.md', 'Markdown (*.md);;Text (*.txt)')
            if not name:
                return False
            path = Path(name)
        try:
            if path.is_symlink():
                raise OSError('Symbolische Links werden nicht ueberschrieben.')
            if path.exists():
                current = path.read_bytes()
                if current != self.disk_baseline:
                    choice = QMessageBox.question(self, 'Datei wurde extern geaendert', 'Den aktuellen Dateiinhalt wirklich ersetzen?')
                    if choice != QMessageBox.StandardButton.Yes:
                        return False
            content = self.text.toPlainText().encode('utf-8')
            fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.pusher-')
            try:
                with os.fdopen(fd, 'wb') as file:
                    file.write(content)
                    file.flush()
                    os.fsync(file.fileno())
                os.replace(temp, path)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
            self.path, self.disk_baseline = path, content
            self.baseline = self.text.toPlainText()
            self.modified()
            self.state.setText('Gespeichert')
            return True
        except OSError:
            QMessageBox.warning(self, 'Speichern fehlgeschlagen', 'Dateipfad, Schreibrechte und freien Speicher pruefen. Text bleibt im Editor erhalten.')
            return False


class ReadmeDialog(QDialog):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.setWindowTitle('README bearbeiten')
        self.resize(880, 660)
        self.setMinimumSize(400, 400)
        layout = QVBoxLayout(self)
        self.editor = MarkdownEditor()
        layout.addWidget(self.editor)
        path = next((p for p in project.iterdir() if p.name.lower() == 'readme.md' and p.is_file()), None)
        if path:
            self.editor.load(path)
        else:
            self.editor.path = project / 'README.md'
            self.editor.set_text('# ' + project.name + '\n\n')

    def reject(self):
        if self.editor.confirm_discard():
            super().reject()

    def closeEvent(self, event):
        event.accept() if self.editor.confirm_discard() else event.ignore()
