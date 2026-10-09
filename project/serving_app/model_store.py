"""Optional immutable bundle archive; local mode never contacts R2."""
import os
from pathlib import Path
import re
import tempfile
from serving_app import runtime as rt

FILES = ('model.keras', 'scaler.pkl', 'manifest.json')


def mode():
    value = os.getenv('SOLAR_MODEL_STORE', 'disabled')
    if value not in ('disabled', 'local', 'r2'):
        raise ValueError('SOLAR_MODEL_STORE must be disabled, local or r2')
    return value


class LocalStore:
    def __init__(self):
        self.root = Path(os.environ['SOLAR_MODEL_ARCHIVE_DIR']).resolve()

    def get(self, key):
        return (self.root / key).read_bytes()

    def put(self, key, data):
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(data)
            try:
                os.link(temporary, path)
            except FileExistsError:
                if path.read_bytes() != data:
                    raise ValueError('Archive object already exists with different content')
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


class R2Store:
    def __init__(self):
        import boto3
        from botocore.config import Config
        from dotenv import dotenv_values
        from urllib.parse import urlparse
        config = {**dotenv_values(rt.PROJECT / '.env'), **os.environ}
        names = ('R2_ENDPOINT_URL', 'R2_BUCKET', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY')
        if not all(config.get(name) for name in names):
            raise ValueError('R2 connection settings are incomplete')
        url = urlparse(config['R2_ENDPOINT_URL'])
        if (url.scheme != 'https' or not (url.hostname or '').endswith('.r2.cloudflarestorage.com')
                or url.username or url.password or url.query or url.fragment or url.path not in ('', '/')):
            raise ValueError('Invalid R2 endpoint')
        self.bucket = config['R2_BUCKET']
        self.client = boto3.client('s3', endpoint_url=config['R2_ENDPOINT_URL'],
            aws_access_key_id=config['R2_ACCESS_KEY_ID'],
            aws_secret_access_key=config['R2_SECRET_ACCESS_KEY'], region_name='auto',
            config=Config(connect_timeout=10, read_timeout=30, retries={'max_attempts': 2}))

    def get(self, key):
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        try:
            return response['Body'].read()
        finally:
            response['Body'].close()

    def put(self, key, data):
        from botocore.exceptions import ClientError
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=data, IfNoneMatch='*')
        except ClientError as exc:
            if exc.response.get('ResponseMetadata', {}).get('HTTPStatusCode') != 412:
                raise
            if self.get(key) != data:
                raise ValueError('Archive object already exists with different content') from None


def store():
    selected = mode()
    if selected == 'disabled':
        return None
    return LocalStore() if selected == 'local' else R2Store()


def receipt_path(pid, version):
    rt.version_dir(pid, version)  # Validate plant and version before constructing paths.
    return rt.plant_dir(pid) / 'archive' / f'{version}.json'


def archive_reference(pid, version):
    path = receipt_path(pid, version)
    if path.exists():
        return rt.read(path)
    from serving_app.registry import client
    tags = client().get_model_version(rt.model_name(pid), str(version)).tags
    if not tags.get('archive_key') or not tags.get('archive_manifest_sha256'):
        raise FileNotFoundError('No archive reference recorded for this model version')
    return dict(key=tags['archive_key'], manifest_sha256=tags['archive_manifest_sha256'])


def validate(directory, pid, version):
    manifest = rt.read(directory / 'manifest.json')
    if (manifest['plant_id'] != pid or str(manifest['version']) != str(version)
            or manifest['contract'] != rt.CONTRACT or manifest['model_name'] != rt.model_name(pid)
            or manifest['gate']['passed'] is not True):
        raise ValueError('Archive bundle identity or approval mismatch')
    for name in FILES[:2]:
        if rt.sha(directory / name) != manifest['hashes'][name]:
            raise ValueError('Archive bundle hash mismatch')
    return manifest


def publish(pid, version):
    backend = store()
    if backend is None:
        return None
    directory = rt.version_dir(pid, version)
    manifest = validate(directory, pid, version)
    # Content address avoids collisions between independently initialized MLflow databases.
    manifest_sha = rt.sha(directory / 'manifest.json')
    key = f'{rt.CONTRACT}/{pid}/{version}/{manifest_sha}'
    for name in FILES:  # Manifest is the completion marker and is always uploaded last.
        data = (directory / name).read_bytes()
        backend.put(f'{key}/{name}', data)
        if backend.get(f'{key}/{name}') != data:
            raise ValueError('Archive upload verification failed')
    receipt = dict(key=key, manifest_sha256=manifest_sha)
    rt.write(receipt_path(pid, version), receipt)
    return receipt


def ensure_local(pid, version):
    directory = rt.version_dir(pid, version)
    if all((directory / name).is_file() for name in FILES):
        return directory
    backend = store()
    if backend is None:
        return directory
    receipt = archive_reference(pid, version)
    expected_key = f'{rt.CONTRACT}/{pid}/{version}/{receipt["manifest_sha256"]}'
    if receipt['key'] != expected_key or not re.fullmatch(r'[0-9a-f]{64}', receipt['manifest_sha256']):
        raise ValueError('Invalid archive receipt')
    directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=directory.parent, prefix='restore-') as staging:
        stage = Path(staging)
        for name in FILES:
            (stage / name).write_bytes(backend.get(f'{expected_key}/{name}'))
        if rt.sha(stage / 'manifest.json') != receipt['manifest_sha256']:
            raise ValueError('Archive manifest hash mismatch')
        validate(stage, pid, version)
        # Never overwrite a partial or concurrently restored cache in place.
        if directory.exists():
            raise ValueError('Incomplete local bundle; move it aside before restoring')
        stage.rename(directory)
    rt.write(receipt_path(pid, version), receipt)
    return directory
