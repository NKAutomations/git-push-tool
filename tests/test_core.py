import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch
from pusher.models import AppError, Cancelled, PushOptions, ReleaseOptions, Release, Asset
from pusher.security import Repository, redact
from pusher.git_service import GitService
from pusher.assets import prepare, upload_files, validate_files, sha256
from pusher.http_client import HttpClient, UploadStream
from pusher.providers import GitHubProvider, GitLabProvider


def git(folder, *args):
    r = subprocess.run(['git', '-C', str(folder), *args], capture_output=True, text=True)
    if r.returncode:
        raise AssertionError(r.stderr)
    return r.stdout.strip()


class GitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = self.root / 'work'
        self.project.mkdir()
        self.remote = self.root / 'remote.git'
        git(self.root, 'init', '--bare', str(self.remote))
        git(self.project, 'init', '-b', 'main')
        git(self.project, 'config', 'user.name', 'Test')
        git(self.project, 'config', 'user.email', 'test@example.invalid')
        self.service = GitService(self.project)
        (self.project / 'a.txt').write_text('initial')

    def tearDown(self):
        self.temp.cleanup()

    def push(self, mode='safe', tag=''):
        return self.service.push(PushOptions(self.project, str(self.remote), 'main', 'test', tag=tag, mode=mode))

    def other_commit(self):
        other = self.root / 'other'
        git(self.root, 'clone', '-b', 'main', str(self.remote), str(other))
        git(other, 'config', 'user.name', 'Other')
        git(other, 'config', 'user.email', 'other@example.invalid')
        (other / 'b.txt').write_text('remote')
        git(other, 'add', '.')
        git(other, 'commit', '-m', 'remote change')
        git(other, 'push', 'origin', 'main')
        return git(other, 'rev-parse', 'HEAD')

    def test_push_and_tag(self):
        report = self.push(tag='v1.0')
        self.assertEqual(report.outcome, 'success')
        self.assertEqual(git(self.remote, 'rev-parse', 'refs/heads/main'), report.commit)
        self.service.verify_tag(str(self.remote), 'v1.0', report.commit)
        self.assertIn('bereits', self.service.push_tag(str(self.remote), 'v1.0', '', report.commit))

    def test_no_change_retry(self):
        self.assertEqual(self.push().outcome, 'success')
        report = self.push()
        self.assertEqual(report.outcome, 'success')
        self.assertEqual(report.steps[0].status, 'skipped')

    def test_divergence_safe(self):
        self.push()
        remote = self.other_commit()
        (self.project / 'c.txt').write_text('local')
        report = self.push()
        self.assertNotEqual(report.outcome, 'success')
        self.assertEqual(git(self.remote, 'rev-parse', 'main'), remote)

    def test_merge(self):
        self.push()
        self.other_commit()
        (self.project / 'c.txt').write_text('local')
        report = self.push('integrate')
        self.assertEqual(report.outcome, 'success')
        self.assertTrue((self.project / 'b.txt').exists())

    def test_explicit_lease(self):
        self.push()
        self.other_commit()
        (self.project / 'c.txt').write_text('local')
        report = self.push('replace')
        self.assertEqual(report.outcome, 'success')
        self.assertEqual(git(self.remote, 'rev-parse', 'main'), report.commit)

    def test_race_lease_rejects(self):
        self.push()
        original = self.service.run
        def racing(*args, **kwargs):
            if args[0] == 'push':
                self.other_commit()
            return original(*args, **kwargs)
        self.service.run = racing
        (self.project / 'c.txt').write_text('local')
        report = self.push('replace')
        self.assertNotEqual(report.outcome, 'success')
        self.assertNotEqual(git(self.remote, 'rev-parse', 'main'), git(self.project, 'rev-parse', 'HEAD'))

    def test_existing_branch_never_reset(self):
        self.push()
        git(self.project, 'branch', 'keep')
        old = git(self.project, 'rev-parse', 'keep')
        report = self.service.push(PushOptions(self.project, str(self.remote), 'keep', 'test'))
        self.assertEqual(report.steps[0].code, 'branch_exists')
        self.assertEqual(git(self.project, 'rev-parse', 'keep'), old)

    def test_tag_failure_partial_success(self):
        initial = self.push(tag='v1')
        (self.project / 'c.txt').write_text('new')
        report = self.push(tag='v1')
        self.assertEqual(report.outcome, 'partial')
        self.assertEqual(report.steps[-1].code, 'tag_mismatch')
        self.assertNotEqual(report.commit, initial.commit)

    def test_cancel(self):
        self.service.cancel.set()
        self.assertEqual(self.push().steps[0].status, 'cancelled')

    def test_invalid_ref(self):
        for name in ('', '-bad', 'a..b', 'a b', 'HEAD'):
            with self.assertRaises(AppError):
                self.service.valid_ref(name)

    def test_new_project_initialization(self):
        project = self.root / 'fresh'
        project.mkdir()
        GitService(project).ensure_project('main')
        self.assertTrue((project / '.git').is_dir())

    def test_nested_rejected(self):
        nested = self.project / 'nested'
        nested.mkdir()
        with self.assertRaises(AppError):
            GitService(nested).ensure_project()


class SecurityTests(unittest.TestCase):
    def test_urls(self):
        self.assertEqual(Repository.parse('git@gitlab.com:team/sub/repo.git', 'GitLab').project, 'team/sub/repo')
        self.assertEqual(Repository.parse('https://github.com/a/b.git', 'GitHub').api_origin, 'https://api.github.com')
        self.assertEqual(Repository.parse('ssh://git@self.example:2222/a/b.git', 'GitLab').web_origin, 'https://self.example')

    def test_rejected_urls(self):
        for url in ('http://github.com/a/b', 'https://token@github.com/a/b', '-u bad',
                    'file:///tmp/x', 'https://github.com/a/b?token=abc', 'https://github.com/a/../b'):
            with self.assertRaises(AppError, msg=url):
                Repository.parse(url, 'GitHub')

    def test_redaction(self):
        raw = 'https://user:secret@example.com/a GH ghp_abcdefgh Authorization: Bearer topsecret ?token=foo glpat-abcdef'
        result = redact(raw)
        for secret in ('user:secret', 'ghp_abcdefgh', 'topsecret', 'token=foo', 'glpat-abcdef'):
            self.assertNotIn(secret, result)


class Response:
    def __init__(self, code=200, payload=None):
        self.status_code = code
        self.payload = payload or {}
        self.content = b'json'
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def json(self): return self.payload


class Session:
    def __init__(self, code=200): self.code, self.calls = code, []
    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return Response(self.code)
    def close(self): pass


class HTTPTests(unittest.TestCase):
    def client(self, status=200):
        return HttpClient(Repository.parse('https://github.com/a/b', 'GitHub'), 'test-secret', Session(status))

    def test_host_block(self):
        client = self.client()
        with self.assertRaises(AppError):
            client.request('GET', 'https://evil.example/upload')
        self.assertEqual(client.session.calls, [])

    def test_status_mapping(self):
        for status in (401, 403, 404, 409, 413, 422, 429, 500, 302):
            with self.assertRaises(AppError) as caught:
                self.client(status).request('POST', 'https://api.github.com/test')
            self.assertEqual(caught.exception.code, 'http_' + str(status))
            self.assertNotIn('test-secret', str(caught.exception))

    def test_missing(self):
        self.assertIsNone(self.client(404).request('GET', 'https://api.github.com/test', missing=True))

    def test_cancel_before_request(self):
        c = self.client()
        c.cancel.set()
        with self.assertRaises(Cancelled):
            c.request('GET', 'https://api.github.com/test')
        self.assertFalse(c.session.calls)

    def test_upload_stream(self):
        import io
        cancel, progress = Event(), []
        stream = UploadStream(io.BytesIO(b'abc'), 3, cancel, lambda s,t: progress.append((s,t)))
        self.assertEqual(stream.read(2), b'ab')
        self.assertEqual(progress[-1], (2,3))
        cancel.set()
        with self.assertRaises(Cancelled): stream.read(2)


GH_ROW = {'id': 5, 'tag_name': 'v1', 'name': 'Title', 'body': 'Notes', 'html_url': 'https://github.com/a/b/releases/tag/v1',
          'upload_url': 'https://uploads.github.com/repos/a/b/releases/5/assets{?name,label}'}


class API:
    def __init__(self): self.calls, self.existing, self.asset_rows = [], False, []
    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if kwargs.get('missing'): return GH_ROW if self.existing else None
        if method in ('POST', 'PATCH'): return GH_ROW
        return {}
    def pages(self, url, params=None):
        return iter(self.asset_rows if url.endswith('/assets') else [])


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.http = API()
        self.provider = GitHubProvider(Repository.parse('https://github.com/a/b', 'GitHub'), self.http)

    def test_github_payload(self):
        release = self.provider.publish(ReleaseOptions('v1', 'Title', 'Notes', draft=True, prerelease=True))
        self.assertEqual(release.id, '5')
        body = self.http.calls[-1][2]['payload']
        self.assertEqual(body['body'], 'Notes')
        self.assertTrue(body['draft'])
        self.assertTrue(body['prerelease'])
        self.assertNotIn('target_commitish', body)

    def test_existing_release_requires_update(self):
        self.http.existing = True
        with self.assertRaises(AppError):
            self.provider.publish(ReleaseOptions('v1', 'Title', 'Notes'))
        self.assertFalse(any(c[0] == 'POST' for c in self.http.calls))

    def test_explicit_update(self):
        self.http.existing = True
        self.provider.publish(ReleaseOptions('v1', 'Title', 'Notes', update=True))
        self.assertEqual(self.http.calls[-1][0], 'PATCH')

    def test_identical_asset_skipped(self):
        self.http.asset_rows = [{'id': 1, 'name': 'a.exe', 'size': 5, 'state': 'uploaded', 'digest': 'sha256:abc'}]
        asset, message = self.provider.upload(self.provider.decode(GH_ROW), Path('a.exe'), 'abc', Event(), lambda *a: None)
        self.assertIn('identisch', message)

    def test_different_asset_blocked(self):
        self.http.asset_rows = [{'id': 1, 'name': 'a.exe', 'size': 5, 'state': 'uploaded', 'digest': 'sha256:def'}]
        with self.assertRaises(AppError):
            self.provider.upload(self.provider.decode(GH_ROW), Path('a.exe'), 'abc', Event(), lambda *a: None)

    def test_gitlab_nested_path(self):
        p = GitLabProvider(Repository.parse('git@gitlab.com:a/b/c.git', 'GitLab'), self.http)
        self.assertTrue(p.base.endswith('/projects/a%2Fb%2Fc'))


class AssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.file = self.root / 'sample.exe'
        self.file.write_bytes(b'example')
    def tearDown(self): self.temp.cleanup()

    def test_duplicate(self):
        with self.assertRaises(AppError): validate_files([self.file, self.file])

    def test_zip_and_checksums(self):
        paths = prepare([self.file], self.root / 'out', True, True, Event())
        self.assertTrue(any(p.name == 'release-bundle.zip' for p in paths))
        sums = next(p for p in paths if p.name == 'SHA256SUMS.txt').read_text()
        self.assertIn(sha256(self.file, Event()), sums)

    def test_partial_upload_and_cancel(self):
        second = self.root / 'other.zip'
        second.write_bytes(b'other')
        class Provider:
            def upload(self, release, path, digest, cancel, progress):
                if path.name == 'other.zip': raise AppError('upload', 'failed')
                return Asset('1', path.name, path.stat().st_size, 'https://example.org/file'), 'ok'
        report = upload_files(Provider(), None, [self.file, second], Event(), lambda *a: None)
        self.assertEqual(report.outcome, 'partial')
        self.assertEqual([s.status for s in report.steps], ['success', 'failed'])
        event = Event(); event.set()
        report = upload_files(Provider(), None, [self.file, second], event, lambda *a: None)
        self.assertEqual([s.status for s in report.steps], ['cancelled', 'cancelled'])



class GitLabAPI:
    def __init__(self):
        self.calls, self.uploads, self.links, self.packages = [], [], [], []
        self.existing = False
        self.fail_link = False
    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if '/assets/links' in url and method == 'POST':
            if self.fail_link: raise AppError('network', 'uncertain link outcome')
            row = {'id': 1, **kwargs['payload']}
            self.links.append(row)
            return row
        if '/compare' in url:
            return {'commits': [{'title': 'Fix *markup*', 'short_id': 'abc123'}]}
        row = {'tag_name': 'v1', 'name': 'Title', 'description': 'Notes', '_links': {'self': 'https://gitlab.com/a/b/-/releases/v1'}}
        if kwargs.get('missing'): return row if self.existing else None
        return row
    def pages(self, url, params=None):
        if url.endswith('/assets/links'): return iter(self.links)
        if url.endswith('/package_files'): return iter(self.files)
        return iter(self.packages)
    def upload(self, method, url, path, cancel, progress):
        self.uploads.append(url)
        import hashlib
        digest = sha256(path, cancel)
        self.packages = [{'id': 10, 'name': 'release-assets', 'version': hashlib.sha256(b'v1').hexdigest()}]
        self.files = [{'file_name': url.rsplit('/', 1)[1], 'file_sha256': digest}]
        progress(path.stat().st_size, path.stat().st_size)
        return {'message': '201 Created'}


class GitLabTests(unittest.TestCase):
    def setUp(self):
        self.api = GitLabAPI()
        self.provider = GitLabProvider(Repository.parse('https://gitlab.com/a/b', 'GitLab'), self.api)
        self.release = Release('v1', 'v1', 'Title', 'Notes', 'https://gitlab.com/a/b/-/releases/v1')
    def test_description_payload(self):
        self.provider.publish(ReleaseOptions('v1', 'Title', 'Notes'))
        self.assertEqual(self.api.calls[-1][2]['payload']['description'], 'Notes')
        self.assertEqual(self.api.calls[-1][0], 'POST')
    def test_update_payload(self):
        self.api.existing = True
        self.provider.publish(ReleaseOptions('v1', 'Title', 'Notes', update=True))
        self.assertEqual(self.api.calls[-1][0], 'PUT')
    def test_draft_rejected(self):
        with self.assertRaises(AppError):
            self.provider.publish(ReleaseOptions('v1', 'Title', 'Notes', draft=True))
        self.assertEqual(self.api.calls, [])
    def test_notes(self):
        with self.assertRaises(AppError): self.provider.generate_notes('v1')
        self.assertIn('abc123', self.provider.generate_notes('v1', 'v0'))
    def test_link_retry_does_not_upload_again(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'app.exe'; path.write_bytes(b'data')
            digest, cancel = sha256(path, Event()), Event()
            self.api.fail_link = True
            with self.assertRaises(AppError):
                self.provider.upload(self.release, path, digest, cancel, lambda *a: None)
            self.api.fail_link = False
            self.provider.upload(self.release, path, digest, cancel, lambda *a: None)
            self.provider.upload(self.release, path, digest, cancel, lambda *a: None)
            self.assertEqual(len(self.api.uploads), 1)
            self.assertEqual(len(self.api.links), 1)
    def test_link_collision(self):
        self.provider.add_link(self.release, 'app.exe', 'https://example.com/old')
        with self.assertRaises(AppError):
            self.provider.add_link(self.release, 'app.exe', 'https://example.com/new')


class MarkdownTests(unittest.TestCase):
    def test_renderer_without_gui_dependency(self):
        # Execute the actual pure rendering function, not a rewritten test implementation.
        import ast
        from markdown_it import MarkdownIt
        source = Path(__file__).parents[1] / 'pusher' / 'editor.py'
        tree = ast.parse(source.read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'render_markdown')
        context = {'MarkdownIt': MarkdownIt}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), context)
        rendered = context['render_markdown']('# Title\n\n**bold**\n\n|a|b|\n|-|-|\n|1|2|\n\n<script>alert(1)</script>\n\n![x](file:///secret)\n\n[x](javascript:alert(1))')
        self.assertIn('<h1>', rendered)
        self.assertIn('<table>', rendered)
        self.assertIn('<strong>', rendered)
        self.assertNotIn('<script>', rendered)
        self.assertNotIn('<img', rendered)
        self.assertNotIn('href="javascript:', rendered)

if __name__ == '__main__': unittest.main()
