import mimetypes
from urllib.parse import urlsplit
from pip_system_certs.wrapt_requests import inject_truststore

# Requests/certifi kennt Unternehmens-CAs oft nicht, die Windows selbst bereits
# vertraut. Der System-Store wird verwendet, ohne Zertifikatsprüfung abzuschalten.
inject_truststore()
import requests
from .models import AppError, Cancelled, checkpoint
from .security import https_url


class UploadStream:
    def __init__(self, file, size, cancel, progress):
        self.file, self.size = file, size
        self.cancel, self.progress = cancel, progress
        self.sent = 0

    def __len__(self):
        return self.size

    def read(self, amount=-1):
        checkpoint(self.cancel)
        chunk = self.file.read(min(amount, 256 * 1024) if amount >= 0 else 256 * 1024)
        self.sent += len(chunk)
        self.progress(self.sent, self.size)
        return chunk


class HttpClient:
    def __init__(self, repository, token, session=None, cancel=None):
        from threading import Event
        self.cancel = cancel or Event()
        if not token or any(c in token for c in '\r\n'):
            raise AppError('auth', 'API-Anmeldung fehlt oder ist ungueltig.')
        self.repository = repository
        self.session = session or requests.Session()
        # Do not pick up .netrc credentials or implicit environment proxies.
        self.session.trust_env = False
        self.headers = {'User-Agent': 'Git-Repository-Pusher/3.0', 'Accept': 'application/json'}
        if repository.provider == 'GitHub':
            self.headers.update(Authorization=f'Bearer {token}', **{'X-GitHub-Api-Version': '2022-11-28'})
        else:
            self.headers['PRIVATE-TOKEN'] = token
        self.allowed = {(urlsplit(repository.api_origin).hostname, urlsplit(repository.api_origin).port or 443)}
        if repository.web_origin == 'https://github.com':
            self.allowed.add(('uploads.github.com', 443))

    def request(self, method, url, *, payload=None, data=None, extra_headers=None, params=None, missing=False):
        checkpoint(self.cancel)
        p = https_url(url)
        if (p.hostname, p.port or 443) not in self.allowed:
            raise AppError('origin', 'API- oder Upload-Host ist nicht fuer diese Anmeldung freigegeben.')
        headers = {**self.headers, **(extra_headers or {})}
        try:
            response = self.session.request(method, url, json=payload, data=data, headers=headers,
                                            params=params, timeout=(10, 30), allow_redirects=False)
        except Cancelled:
            raise
        except requests.RequestException:
            raise AppError('network', 'Netzwerk- oder TLS-Fehler. Ergebnis kann unklar sein; vor erneutem Schreiben Remote-Stand pruefen.', True) from None
        with response:
            code = response.status_code
            if missing and code == 404:
                return None
            if not 200 <= code < 300:
                labels = {401: 'API-Anmeldung ungueltig.', 403: 'Berechtigung, Schutzregel oder Rate-Limit pruefen.',
                          404: 'Ressource fehlt oder ist fuer diese Anmeldung nicht sichtbar.',
                          409: 'Konflikt mit vorhandenem Stand.', 413: 'Datei ist fuer den Server zu gross.',
                          422: 'Server lehnt Eingaben ab; Tag, Dateiname und vorhandene Assets pruefen.',
                          429: 'Rate-Limit erreicht. Spaeter erneut versuchen.'}
                message = labels.get(code, 'API-Anfrage fehlgeschlagen; Serverstatus und Konfiguration pruefen.')
                if 300 <= code < 400:
                    message = 'Weiterleitung aus Sicherheitsgruenden nicht verfolgt. Exakten API-Host verwenden.'
                # Never display untrusted server bodies/headers: they may echo credentials.
                raise AppError(f'http_{code}', f'HTTP {code}: {message}', code == 429 or code >= 500)
            if code == 204 or not response.content:
                return {}
            try:
                return response.json()
            except ValueError:
                raise AppError('json', 'Server lieferte keine gueltige JSON-Antwort.') from None

    def pages(self, url, params=None):
        for page in range(1, 10001):
            rows = self.request('GET', url, params={**(params or {}), 'per_page': 100, 'page': page})
            if not isinstance(rows, list):
                raise AppError('schema', 'Unerwartetes API-Antwortformat.')
            yield from rows
            if len(rows) < 100:
                return
        raise AppError('pagination', 'Zu viele Ergebnisse. Vorgang sicher abgebrochen.')

    def upload(self, method, url, path, cancel, progress, params=None):
        checkpoint(cancel)
        with path.open('rb') as file:
            import os
            size = os.fstat(file.fileno()).st_size
            stream = UploadStream(file, size, cancel, progress)
            result = self.request(method, url, data=stream if size else b'', params=params,
                                  extra_headers={'Content-Type': mimetypes.guess_type(path.name)[0] or 'application/octet-stream',
                                                 'Content-Length': str(size)})
            # A cancellation after server acknowledgement must not erase a success.
            progress(size, size)
            return result

    def close(self):
        self.headers.clear()
        self.session.close()
