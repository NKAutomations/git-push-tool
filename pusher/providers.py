from abc import ABC, abstractmethod
from urllib.parse import quote
import hashlib
from .models import AppError, Release, Asset, checkpoint
from .security import https_url


def q(value):
    return quote(str(value), safe='')


class ReleaseProvider(ABC):
    def __init__(self, repository, client):
        self.repository, self.http = repository, client

    @abstractmethod
    def find(self, tag): ...

    @abstractmethod
    def publish(self, options): ...

    @abstractmethod
    def assets(self, release): ...

    @abstractmethod
    def upload(self, release, path, digest, cancel, progress): ...

    @abstractmethod
    def generate_notes(self, tag, previous=''): ...


class GitHubProvider(ReleaseProvider):
    @property
    def base(self):
        path = '/'.join(q(s) for s in self.repository.project.split('/'))
        return self.repository.api_origin + '/repos/' + path

    @staticmethod
    def decode(row):
        return Release(str(row['id']), row['tag_name'], row.get('name') or '', row.get('body') or '',
                       row['html_url'], row['upload_url'].split('{', 1)[0],
                       bool(row.get('draft')), bool(row.get('prerelease')))

    def find(self, tag):
        row = self.http.request('GET', self.base + '/releases/tags/' + q(tag), missing=True)
        if row:
            return self.decode(row)
        # Include drafts visible to the authenticated account.
        for row in self.http.pages(self.base + '/releases'):
            if row['tag_name'] == tag:
                return self.decode(row)
        return None

    def publish(self, options):
        # No target_commitish: do not silently create tags as part of a release.
        self.http.request('GET', self.base + '/git/ref/tags/' + q(options.tag))
        existing = self.find(options.tag)
        body = {'tag_name': options.tag, 'name': options.title, 'body': options.notes,
                'draft': options.draft, 'prerelease': options.prerelease}
        if existing:
            if not options.update:
                raise AppError('release_exists', 'Release existiert bereits. Laden und Aktualisierung bewusst aktivieren.')
            row = self.http.request('PATCH', self.base + '/releases/' + q(existing.id), payload=body)
        else:
            if options.update:
                raise AppError('release_missing', 'Zu aktualisierendes Release fehlt. Aktualisierungsmodus deaktivieren.')
            row = self.http.request('POST', self.base + '/releases', payload=body)
        return self.decode(row)

    def generate_notes(self, tag, previous=''):
        body = {'tag_name': tag}
        if previous:
            body['previous_tag_name'] = previous
        row = self.http.request('POST', self.base + '/releases/generate-notes', payload=body)
        return row.get('body', '')

    def assets(self, release):
        return [Asset(str(r['id']), r['name'], r.get('size', 0), r.get('browser_download_url', ''),
                      (r.get('digest') or '').removeprefix('sha256:'), r.get('state', ''))
                for r in self.http.pages(self.base + '/releases/' + q(release.id) + '/assets')]

    def upload(self, release, path, digest, cancel, progress):
        checkpoint(cancel)
        for asset in self.assets(release):
            if asset.name.casefold() == path.name.casefold():
                if asset.state == 'uploaded' and asset.digest == digest:
                    return asset, 'Bereits identisch vorhanden; nicht erneut hochgeladen.'
                raise AppError('asset_exists', 'Asset-Name bereits belegt. Ohne passende SHA-256 kein automatisches Ersetzen; Datei umbenennen oder Asset bewusst auf GitHub entfernen.')
        row = self.http.upload('POST', release.upload_url, path, cancel, progress, params={'name': path.name})
        if row.get('state') != 'uploaded' or row.get('size') != path.stat().st_size:
            raise AppError('asset_unverified', 'Upload nicht vollstaendig bestaetigt. Vor erneutem Versuch Assets pruefen.', True)
        actual = (row.get('digest') or '').removeprefix('sha256:')
        if actual and actual != digest:
            raise AppError('asset_digest', 'SHA-256 des Server-Assets weicht ab. Asset vor weiterer Nutzung pruefen.')
        return Asset(str(row['id']), row['name'], row['size'], row['browser_download_url'], actual), 'Hochgeladen.'


class GitLabProvider(ReleaseProvider):
    @property
    def base(self):
        return self.repository.api_origin + '/projects/' + q(self.repository.project)

    def decode(self, row):
        return Release(row['tag_name'], row['tag_name'], row.get('name', ''), row.get('description') or '',
                       row.get('_links', {}).get('self') or self.repository.web_origin + '/' + self.repository.project + '/-/releases/' + q(row['tag_name']))

    def find(self, tag):
        row = self.http.request('GET', self.base + '/releases/' + q(tag), missing=True)
        return self.decode(row) if row else None

    def publish(self, options):
        if options.draft or options.prerelease:
            raise AppError('unsupported', 'Draft und Pre-Release sind hier nur fuer GitHub verfuegbar.')
        self.http.request('GET', self.base + '/repository/tags/' + q(options.tag))
        existing = self.find(options.tag)
        body = {'name': options.title, 'description': options.notes}
        if existing:
            if not options.update:
                raise AppError('release_exists', 'Release existiert bereits. Zuerst laden und Aktualisierung aktivieren.')
            row = self.http.request('PUT', self.base + '/releases/' + q(options.tag), payload=body)
        else:
            if options.update:
                raise AppError('release_missing', 'Zu aktualisierendes Release fehlt.')
            row = self.http.request('POST', self.base + '/releases', payload={**body, 'tag_name': options.tag})
        return self.decode(row)

    def generate_notes(self, tag, previous=''):
        if not previous:
            raise AppError('previous_tag', 'Fuer GitLab einen vorherigen Tag fuer den Commit-Vergleich eingeben.')
        row = self.http.request('GET', self.base + '/repository/compare', params={'from': previous, 'to': tag, 'straight': 'true'})
        if row.get('compare_timeout'):
            raise AppError('compare_timeout', 'Commit-Vergleich unvollstaendig. Notes manuell erstellen.')
        # Plain text titles are escaped before insertion into Markdown.
        def escape(text):
            import re
            return re.sub(r'([\\`*_{}\[\]()#+.!<>|~-])', r'\\\1', text.replace('\n', ' '))
        return '# Aenderungen\n\n' + '\n'.join('- ' + escape(c['title']) + ' (`' + c['short_id'] + '`)' for c in row.get('commits', []))

    def assets(self, release):
        return [Asset(str(r['id']), r['name'], 0, r['url']) for r in
                self.http.pages(self.base + '/releases/' + q(release.tag) + '/assets/links')]

    def add_link(self, release, name, url):
        https_url(url)
        for asset in self.assets(release):
            if asset.name.casefold() == name.casefold():
                if asset.url == url:
                    return asset
                raise AppError('asset_exists', 'Ein anderer Asset-Link verwendet bereits diesen Namen.')
        row = self.http.request('POST', self.base + '/releases/' + q(release.tag) + '/assets/links',
                                payload={'name': name, 'url': url, 'link_type': 'other'})
        return Asset(str(row['id']), row['name'], 0, row['url'])

    def upload(self, release, path, digest, cancel, progress):
        checkpoint(cancel)
        # Content-addressed filenames avoid silently overwriting a different binary.
        # A hash of the tag is a legal package version even for tags containing '/'.
        version = hashlib.sha256(release.tag.encode()).hexdigest()
        filename = digest + '-' + path.name
        url = self.base + '/packages/generic/release-assets/' + version + '/' + filename
        existing_link = None
        for asset in self.assets(release):
            if asset.name.casefold() == path.name.casefold():
                if asset.url != url:
                    raise AppError('asset_exists', 'Asset-Name bereits fuer anderen Inhalt vergeben; Datei umbenennen.')
                existing_link = asset
        present = False
        for package in self.http.pages(self.base + '/packages', {'package_type': 'generic', 'package_name': 'release-assets', 'package_version': version}):
            if package.get('name') != 'release-assets' or package.get('version') != version:
                continue
            for file in self.http.pages(self.base + '/packages/' + q(package['id']) + '/package_files'):
                if file['file_name'] == filename:
                    if file.get('file_sha256') != digest:
                        raise AppError('asset_digest', 'Vorhandene Package-Datei hat unerwartete SHA-256.')
                    present = True
        if not present:
            self.http.upload('PUT', url, path, cancel, progress)
        elif existing_link:
            return existing_link, 'Package-Pruefsumme und vorhandener Asset-Link bestaetigt.'
        checkpoint(cancel)
        # Retry after failed link creation finds the package and only adds the missing link.
        asset = self.add_link(release, path.name, url)
        return asset, 'Package hochgeladen und mit Release verknuepft.'


def provider_for(repository, client):
    return (GitHubProvider if repository.provider == 'GitHub' else GitLabProvider)(repository, client)
