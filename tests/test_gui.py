"""Real Qt smoke tests, skipped if the optional GUI runtime is unavailable."""
import os
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 unavailable: GUI not tested here')
class QtSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
    def test_main_window_small(self):
        from pusher.gui import MainWindow
        window = MainWindow()
        window.resize(420, 540)
        window.show()
        self.app.processEvents()
        self.assertEqual(window.controls.count(), 2)
        self.assertFalse(window.open_last_release_button.isEnabled())
        window.close()

    def test_release_context_order(self):
        from pusher.gui import MainWindow
        from pusher.security import Repository
        window = MainWindow()
        project = Path(tempfile.gettempdir())
        repository = Repository.parse('https://github.com/a/b', 'GitHub')
        with patch('pusher.gui.ReleaseDialog') as dialog_class:
            dialog_class.return_value.exec.return_value = 0
            window.show_release((project, repository, 'v1', 'a' * 40))
            dialog_class.assert_called_once_with(repository, project, 'v1', 'a' * 40, window)
        window.close()
    def test_release_views(self):
        from pusher.gui import ReleaseDialog
        from pusher.security import Repository
        with tempfile.TemporaryDirectory() as folder:
            for provider, url in [('GitHub', 'https://github.com/a/b'), ('GitLab', 'https://gitlab.com/a/b')]:
                dialog = ReleaseDialog(Repository.parse(url, provider), Path(folder), 'v1', 'a'*40)
                self.assertEqual(dialog.controls.count(), 3)
                self.assertEqual(dialog.draft.isEnabled(), provider == 'GitHub')
                dialog.reject()
    def test_editor_preview(self):
        from pusher.editor import MarkdownEditor
        editor = MarkdownEditor()
        editor.set_text('# Heading\n\n**text**')
        editor.tabs.setCurrentIndex(1)
        self.assertIn('Heading', editor.preview.toPlainText())
        self.assertTrue(editor.dirty)
        editor.deleteLater()
