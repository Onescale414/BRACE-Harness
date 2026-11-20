"""Bounded byte storage; validation and authorization belong to the caller.

The stable advisory lock coordinates cooperating processes. Path/identity checks
reject common linked-file mistakes; they are not a hostile-writer security
boundary. Staging files are fsynced, but two-file transactions and power-loss
durability are not promised. A failed publication can refresh previous to the
unchanged current. Unknown staging files are preserved and require host action.
"""
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat
import time


MAX_BYTES = 65536
CURRENT = 'lessons.json'
PREVIOUS = 'lessons.previous.json'
LOCK = 'lessons.lock'
STAGES = (CURRENT + '.next', PREVIOUS + '.next')


class StoreError(RuntimeError):
    """An unavailable, stale, unsafe, or failed byte store."""


class StoreBusy(StoreError):
    pass


class StoreDeadline(StoreError):
    pass


class StoreUncertain(StoreError):
    """Publication was attempted, but its outcome cannot be confirmed."""


def _identity(info):
    return info.st_dev, info.st_ino


def _stamp(info):
    # Windows stat/fstat can report different ctime meanings on Python 3.13.
    return (_identity(info), info.st_size, info.st_mtime_ns)


def _linked(info):
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, 'st_file_attributes', 0) & 0x400)


def _regular(info):
    if _linked(info) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise StoreError('store file must be regular, unlinked, and not a reparse point')


@dataclass(frozen=True)
class _Snapshot:
    identity: tuple
    size: int
    digest: str


@dataclass
class _Stage:
    path: Path
    identity: tuple
    payload: bytes
    written: int = 0


class Store:
    """Hold an exclusive nonblocking OS lock for one context.

    ``directory`` must be an absolute host-provided path with existing parents.
    Only its final component may be created. Reads are at most MAX_BYTES + 1;
    only hashes, sizes, and identities survive between operations.
    """

    def __init__(self, directory):
        self.directory = Path(directory)
        if (not self.directory.is_absolute() or '..' in self.directory.parts
                or self.directory.drive.startswith('\\\\')):
            raise StoreError('store directory must be local and absolute without parent traversal')
        self._directories = {}
        self._expected = {}
        self._lock_fd = None
        self._lock_identity = None
        self._entered = False
        self._uncertain = False

    def _check_directories(self, *, initialize=False):
        for path in reversed((self.directory, *self.directory.parents)):
            try:
                info = path.lstat()
            except FileNotFoundError:
                if not initialize or path != self.directory:
                    raise StoreError('store parent directory does not exist') from None
                try:
                    # Python 3.13's Windows 0700 ACL excludes restricted host
                    # tokens. Inherit the host-selected parent ACL on Windows.
                    path.mkdir(mode=0o777 if os.name == 'nt' else 0o700)
                except FileExistsError:
                    pass
                info = path.lstat()
            if _linked(info) or not stat.S_ISDIR(info.st_mode):
                raise StoreError('store directories must not contain symlinks or reparse points')
            if initialize:
                self._directories[path] = _identity(info)
            elif self._directories.get(path) != _identity(info):
                raise StoreError('store directory identity changed')

    def _check_lock(self):
        self._check_directories()
        info = (self.directory / LOCK).lstat()
        _regular(info)
        held = os.fstat(self._lock_fd)
        _regular(held)
        if _identity(info) != self._lock_identity or _identity(held) != self._lock_identity:
            raise StoreError('store lock identity changed')

    def _require_open(self):
        if not self._entered or self._uncertain:
            raise StoreError('store requires an open, verified context')
        self._check_lock()

    def _read_file(self, path):
        self._check_directories()
        try:
            before = path.lstat()
        except FileNotFoundError:
            return None, None
        _regular(before)
        flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
        fd = os.open(path, flags)
        with os.fdopen(fd, 'rb') as stream:
            opened = os.fstat(stream.fileno())
            _regular(opened)
            if _stamp(opened) != _stamp(before):
                raise StoreError('store file changed while opening')
            payload = stream.read(MAX_BYTES + 1)
            after = os.fstat(stream.fileno())
            _regular(after)
            if len(payload) > MAX_BYTES or after.st_size > MAX_BYTES:
                raise StoreError('store file exceeds byte limit')
            if _stamp(opened) != _stamp(after) or len(payload) != after.st_size:
                raise StoreError('store file changed while reading')
        named = path.lstat()
        _regular(named)
        if _stamp(named) != _stamp(after):
            raise StoreError('store file identity changed while reading')
        return payload, _Snapshot(_identity(after), len(payload), hashlib.sha256(payload).hexdigest())

    def _no_stages(self):
        for name in STAGES:
            try:
                (self.directory / name).lstat()
            except FileNotFoundError:
                continue
            raise StoreError('unrecognized staging file; refusing automatic repair')

    def __enter__(self):
        if self._entered or self._lock_fd is not None:
            raise StoreError('store context is already open')
        try:
            self._check_directories(initialize=True)
            path = self.directory / LOCK
            flags = os.O_RDWR | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
            try:
                fd = os.open(path, flags | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                _regular(path.lstat())
                fd = os.open(path, flags)
            self._lock_fd = fd
            info = os.fstat(fd)
            _regular(info)
            _regular(path.lstat())
            self._lock_identity = _identity(info)
            self._check_lock()
            try:
                if os.name == 'nt':
                    import msvcrt
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise StoreBusy('store is already locked or locking is unavailable') from exc
            if info.st_size == 0:
                os.lseek(fd, 0, os.SEEK_SET)
                os.write(fd, b'\0')
                os.fsync(fd)
            self._check_lock()
            self._no_stages()
            for name in (CURRENT, PREVIOUS):
                _, self._expected[name] = self._read_file(self.directory / name)
            self._uncertain = False
            self._entered = True
            return self
        except Exception as exc:
            self.__exit__(None, None, None)
            if isinstance(exc, StoreError):
                raise
            raise StoreError('cannot open store: ' + str(exc)) from exc

    def __exit__(self, exc_type, exc_value, traceback):
        self._entered = False
        fd, self._lock_fd = self._lock_fd, None
        if fd is not None:
            # Closing the descriptor releases the kernel lock, including after
            # partial entry failure. The stable file is deliberately retained.
            os.close(fd)
        return False

    def _read_expected(self, name):
        payload, snapshot = self._read_file(self.directory / name)
        if snapshot != self._expected[name]:
            raise StoreError('store contents or file identity changed outside this context')
        return payload

    def read(self):
        try:
            self._require_open()
            return self._read_expected(CURRENT)
        except OSError as exc:
            raise StoreError('cannot read store: ' + str(exc)) from exc

    def read_previous(self):
        try:
            self._require_open()
            return self._read_expected(PREVIOUS)
        except OSError as exc:
            raise StoreError('cannot read previous store: ' + str(exc)) from exc

    def _stage(self, name, payload, owned):
        path = self.directory / (name + '.next')
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0)
        fd = os.open(path, flags, 0o600)
        stage = _Stage(path, _identity(os.fstat(fd)), payload)
        owned.append(stage)
        with os.fdopen(fd, 'wb', buffering=0) as stream:
            while stage.written < len(payload):
                count = stream.write(memoryview(payload)[stage.written:])
                if not count:
                    raise StoreError('staging write made no progress')
                stage.written += count
            stream.flush()
            os.fsync(stream.fileno())
        self._verify_stage(stage)
        return stage

    def _verify_stage(self, stage):
        payload, snapshot = self._read_file(stage.path)
        if snapshot is None or snapshot.identity != stage.identity or payload != stage.payload:
            raise StoreError('staging file changed')

    def _cleanup(self, owned):
        for stage in owned:
            try:
                payload, snapshot = self._read_file(stage.path)
                if (snapshot is not None and snapshot.identity == stage.identity
                        and payload == stage.payload[:stage.written]):
                    stage.path.unlink()
            except (OSError, StoreError):
                # An unknown file, replaced path, or uncertain write is never
                # deleted merely because it occupies our staging filename.
                pass

    @staticmethod
    def _deadline(deadline_ns, clock):
        if deadline_ns is not None and clock() >= deadline_ns:
            raise StoreDeadline('store commit deadline expired')

    def commit(self, payload, *, deadline_ns=None, clock=time.monotonic_ns):
        if type(payload) is not bytes or len(payload) > MAX_BYTES:
            raise StoreError('commit requires bytes within the byte limit')
        owned, warnings = [], []
        published = attempted = False
        current_stage = None
        previous_digest = None
        try:
            self._require_open()
            self._deadline(deadline_ns, clock)
            self._no_stages()
            old_current = self._read_expected(CURRENT)
            self._read_expected(PREVIOUS)
            current_stage = self._stage(CURRENT, payload, owned)
            backup_stage = (self._stage(PREVIOUS, old_current, owned)
                            if old_current is not None else None)
            self._require_open()
            self._read_expected(CURRENT)
            self._read_expected(PREVIOUS)
            self._verify_stage(current_stage)
            if backup_stage is not None:
                self._verify_stage(backup_stage)
                self._deadline(deadline_ns, clock)
                try:
                    os.replace(backup_stage.path, self.directory / PREVIOUS)
                finally:
                    # A replace wrapper can report failure after publishing.
                    # Record a recognizable backup so a retry does not mistake
                    # our own completed backup for an external modification.
                    if not backup_stage.path.exists():
                        backup, snapshot = self._read_file(self.directory / PREVIOUS)
                        if backup == old_current:
                            self._expected[PREVIOUS] = snapshot
                self._read_expected(PREVIOUS)
            previous = self._expected[PREVIOUS]
            previous_digest = previous.digest if previous is not None else None
            self._require_open()
            self._read_expected(CURRENT)
            self._read_expected(PREVIOUS)
            self._verify_stage(current_stage)
            self._deadline(deadline_ns, clock)  # Final check immediately before publication.
            attempted = True
            os.replace(current_stage.path, self.directory / CURRENT)
            published = True
        except Exception as exc:
            if attempted and not published:
                try:
                    actual, _ = self._read_file(self.directory / CURRENT)
                    stage_exists = current_stage.path.exists()
                    published = actual == payload and not stage_exists
                    if not published and not stage_exists:
                        raise StoreError('publication evidence is inconsistent')
                except (OSError, StoreError):
                    self._uncertain = True
                    raise StoreUncertain('store publication outcome is unconfirmed') from exc
            if not published:
                if isinstance(exc, StoreError):
                    raise
                raise StoreError('store commit failed: ' + str(exc)) from exc
            warnings.append('publication-reported-error')
        finally:
            if not self._uncertain:
                self._cleanup(owned)
        try:
            actual, snapshot = self._read_file(self.directory / CURRENT)
            if actual != payload:
                raise StoreError('published file could not be verified')
            self._expected[CURRENT] = snapshot
            self._check_lock()
        except (OSError, StoreError):
            self._uncertain = True
            warnings.append('reopen-required')
        # No deadline check or rollback is allowed after publication.
        return {'committed': True, 'sha256': hashlib.sha256(payload).hexdigest(),
                'previous_sha256': previous_digest, 'bytes': len(payload),
                'warnings': warnings, 'reopen_required': self._uncertain}
