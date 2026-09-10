"""Persistent non-secret settings and Windows Credential Manager access."""
import json
import os
from pathlib import Path

from .models import AppError


APP_NAME = 'GitRepositoryPusher'
CONFIG_VERSION = 1


class ConfigStore:
    def __init__(self, path=None):
        appdata = Path(os.environ.get('APPDATA', Path.home() / 'AppData' / 'Roaming'))
        self.path = Path(path) if path else appdata / APP_NAME / 'config.json'

    def load(self):
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            return {}
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {}
        if not isinstance(data, dict) or data.get('version') != CONFIG_VERSION:
            return {}
        return data.get('settings', {}) if isinstance(data.get('settings', {}), dict) else {}

    def save(self, settings):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({'version': CONFIG_VERSION, 'settings': settings},
                             ensure_ascii=False, indent=2) + '\n'
        temp = self.path.with_suffix('.tmp')
        temp.write_text(payload, encoding='utf-8')
        os.replace(temp, self.path)

    def export(self, path, settings):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({'version': CONFIG_VERSION, 'settings': settings},
                             ensure_ascii=False, indent=2) + '\n'
        temp = path.with_suffix(path.suffix + '.tmp')
        temp.write_text(payload, encoding='utf-8')
        os.replace(temp, path)

    def import_file(self, path):
        path = Path(path)
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise AppError('config', 'Konfiguration konnte nicht gelesen werden.') from None
        if not isinstance(data, dict) or data.get('version') != CONFIG_VERSION or not isinstance(data.get('settings'), dict):
            raise AppError('config', 'Unbekanntes oder inkompatibles Konfigurationsformat.')
        return data['settings']


class CredentialStore:
    service = 'NKAutomations.GitRepositoryPusher'

    @staticmethod
    def _backend():
        try:
            import keyring
            return keyring.get_keyring()
        except Exception:
            return None

    @classmethod
    def key(cls, repository):
        return f'{repository.provider}/{repository.host}/{repository.project}'

    @classmethod
    def get(cls, repository):
        backend = cls._backend()
        if backend is None:
            return ''
        try:
            return backend.get_password(cls.service, cls.key(repository)) or ''
        except Exception:
            return ''

    @classmethod
    def set(cls, repository, token):
        backend = cls._backend()
        if backend is None:
            raise AppError('credential_store', 'Windows Credential Manager ist nicht verfügbar; Token wird nicht gespeichert.')
        try:
            backend.set_password(cls.service, cls.key(repository), token)
        except Exception:
            raise AppError('credential_store', 'Token konnte nicht im Windows Credential Manager gespeichert werden.') from None
