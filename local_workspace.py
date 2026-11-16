"""Per-run LOCAL disk workspace and crash-recoverable staged publication.

No IFC transformation logic lives here.  Recovery is cooperative: abnormal
process termination is recovered on the next launch, not at the instant of exit.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path

ROOT_NAME = 'IFCMaterialFilter'
RUNS_NAME = 'Work'
META_NAME = 'run.json'
LOCK_NAME = '.run.lock'


def _is_local_fixed(path: Path) -> bool:
    if os.name != 'nt':
        return True
    import ctypes
    root = Path(path).anchor
    if not root or root.startswith('\\\\'):
        return False
    return ctypes.windll.kernel32.GetDriveTypeW(str(root)) == 3  # DRIVE_FIXED


def workspace_root() -> Path:
    """Choose a real local fixed disk on Windows (never network/UNC)."""
    candidates = [os.environ.get('LOCALAPPDATA'), os.environ.get('TEMP'),
                  os.environ.get('TMP'), os.environ.get('USERPROFILE')]
    if os.name != 'nt':
        candidates = [os.environ.get('XDG_CACHE_HOME'), tempfile.gettempdir()]
    for location in candidates:
        if not location:
            continue
        path = Path(location).expanduser().resolve()
        if _is_local_fixed(path):
            return path / ROOT_NAME / RUNS_NAME
    raise RuntimeError('No local fixed-disk temporary workspace found. '
                       'Check LOCALAPPDATA/TEMP settings; network temp storage is not permitted.')


def _lock(handle, blocking=False):
    if os.name == 'nt':
        import msvcrt
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True
    import fcntl
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
    except (OSError, BlockingIOError):
        return False
    return True


def _unlock(handle):
    if os.name == 'nt':
        import msvcrt
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _safe_staging(metadata, run_id):
    """Never remove files other than the exact staging name created by us."""
    destination = metadata.get('destination')
    if not destination:
        return None
    dest = Path(destination)
    expected = f'{dest.name}.{run_id}.publishing.incomplete.ifc'
    return dest.with_name(expected)


def recover_abandoned(root=None, notify=print):
    """Clean only valid, unlocked run-UUID workspaces; do not touch live runs."""
    root = Path(root) if root else workspace_root()
    recovered = 0
    if not root.is_dir():
        return recovered
    for child in root.iterdir():
        try:
            run_id = child.name.removeprefix('run-')
            if not child.is_dir() or not child.name.startswith('run-'):
                continue
            if str(uuid.UUID(run_id)) != run_id or child.is_symlink():
                continue
            meta_path, lock_path = child / META_NAME, child / LOCK_NAME
            if not meta_path.is_file() or not lock_path.is_file():
                continue
            with lock_path.open('r+b') as fh:
                if not _lock(fh):
                    continue
                try:
                    metadata = json.loads(meta_path.read_text(encoding='utf-8'))
                    if metadata.get('id') != run_id or metadata.get('owner') != ROOT_NAME:
                        continue
                    staging = _safe_staging(metadata, run_id)
                    if staging is not None:
                        try:
                            staging.unlink(missing_ok=True)
                        except OSError as error:
                            notify(f'WARNING: Abandoned destination staging file could not be removed: {error}')
                            raise
                    # Keep metadata until all temporary content is deleted.
                    # If deletion fails, the next launch can retry recovery.
                    for entry in child.iterdir():
                        if entry not in (lock_path, meta_path):
                            if entry.is_symlink() or entry.is_file():
                                entry.unlink()
                            elif entry.is_dir():
                                shutil.rmtree(entry)
                    meta_path.unlink()
                    recovered += 1
                finally:
                    try:
                        _unlock(fh)
                    except OSError:
                        pass
            lock_path.unlink(missing_ok=True)
            try:
                child.rmdir()
            except OSError:
                pass
        except (OSError, ValueError, json.JSONDecodeError) as error:
            notify(f'WARNING: Workspace recovery skipped {child.name}: {error}')
    if recovered:
        notify(f'Recovered {recovered} abandoned local IFC workspace(s).')
    return recovered


class LocalWorkspace:
    def __init__(self, destination, root=None, notify=print, source_bytes=0):
        self.root = Path(root) if root else workspace_root()
        self.destination = Path(destination).absolute()
        self.notify = notify
        self.run_id = str(uuid.uuid4())
        self.directory = self.root / ('run-' + self.run_id)
        self.raw = self.directory / 'unpruned.ifc'
        self.pruned = self.directory / 'pruned.ifc'
        self.staging = _safe_staging({'destination': str(self.destination)}, self.run_id)
        self.lock_handle = None
        self.source_bytes = source_bytes

    def __enter__(self):
        self.root.mkdir(parents=True, exist_ok=True)
        # Explicit disk-space requirement: the source may expand in serialization.
        free = shutil.disk_usage(self.root).free
        required = max(1024**3, 3 * self.source_bytes + 512 * 1024**2)
        if free < required:
            raise OSError(f'Insufficient local scratch space: {free / 1024**3:.2f} GiB free; '
                          f'at least {required / 1024**3:.2f} GiB required. '
                          f'Local workspace parent: {self.root}')
        self.directory.mkdir(mode=0o700, exist_ok=False)
        try:
            self.lock_handle = (self.directory / LOCK_NAME).open('w+b')
            self.lock_handle.write(b'1')
            self.lock_handle.flush()
            if not _lock(self.lock_handle):
                raise RuntimeError('Could not lock local IFC workspace')
            meta = {'owner': ROOT_NAME, 'id': self.run_id,
                    'destination': str(self.destination)}
            (self.directory / META_NAME).write_text(json.dumps(meta), encoding='utf-8')
            self.notify(f'Local IFC workspace: {self.directory} '
                        f'({free / 1024**3:.2f} GiB free)')
            return self
        except BaseException:
            self._cleanup()
            raise

    def publish(self, validated_ifc):
        """Stage on destination filesystem; final name never exposes partial bytes."""
        src, dest = Path(validated_ifc), self.destination
        if dest.exists():
            raise FileExistsError(f'Final output already exists: {dest}')
        dest.parent.mkdir(parents=True, exist_ok=True)
        self.notify(f'Publishing validated IFC to destination: {dest}')
        try:
            # x+b refuses stale or competing staging files.
            with self.staging.open('x+b') as out, src.open('rb') as source:
                shutil.copyfileobj(source, out, length=8 * 1024 * 1024)
                out.flush()
                os.fsync(out.fileno())
            if dest.exists():
                raise FileExistsError(f'Final output appeared during publication: {dest}')
            # On Windows/SMB, rename into existing path fails. On POSIX,
            # hardlink ensures no overwrite; rename fallback only on Windows.
            if os.name == 'nt':
                os.rename(self.staging, dest)
            else:
                os.link(self.staging, dest)
                self.staging.unlink()
            self.notify(f'Published validated IFC: {dest}')
        except BaseException:
            try:
                self.staging.unlink(missing_ok=True)
            except OSError as error:
                self.notify(f'WARNING: Destination staging cleanup failed: {error}')
            raise

    def _cleanup(self):
        staging_clean = True
        try:
            self.staging.unlink(missing_ok=True)
        except OSError as error:
            staging_clean = False
            self.notify(f'WARNING: Could not remove destination staging: {error}')
        # Windows cannot unlink an open locked file. Remove everything else
        # while owning the lock, then release it before deleting lock file.
        if self.directory.is_dir():
            try:
                for entry in self.directory.iterdir():
                    if entry.name in (LOCK_NAME, META_NAME):
                        continue
                    if entry.is_file() or entry.is_symlink():
                        entry.unlink()
                    elif entry.is_dir():
                        shutil.rmtree(entry)
                if staging_clean:
                    (self.directory / META_NAME).unlink(missing_ok=True)
            except OSError as error:
                self.notify(f'WARNING: Could not clean local workspace: {error}. '
                            'It will be retried on the next launch.')
        if self.lock_handle is not None:
            try:
                _unlock(self.lock_handle)
                self.lock_handle.close()
            except OSError:
                pass
            self.lock_handle = None
        if not (self.directory / META_NAME).exists():
            try:
                (self.directory / LOCK_NAME).unlink(missing_ok=True)
                self.directory.rmdir()
            except OSError as error:
                self.notify(f'WARNING: Could not finalize local workspace removal: {error}')

    def __exit__(self, exc_type, exc, tb):
        self._cleanup()
        return False
