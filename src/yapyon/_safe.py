"""Private staging and checked Linux replacement for prepared record text.

Linux POSIX access ACLs and security labels are inspected explicitly. Other
platforms are refused. Conflict checks are not a filesystem lock or an atomic
compare-and-swap against hostile concurrent pathname changes.
"""

from __future__ import annotations

from dataclasses import dataclass
import errno
import os
import stat
import sys
import tempfile


@dataclass
class _Candidate:
    path: str | None = None
    directory: str | None = None
    fd: int | None = None
    directory_fd: int | None = None
    parent_fd: int | None = None
    identity: tuple | None = None
    directory_identity: tuple | None = None
    written: bool = False
    complete: bool = False
    close_failed: bool = False


def _identity(info):
    return info.st_dev, info.st_ino


def _signature(info):
    return (_identity(info), info.st_mode, info.st_uid, info.st_gid,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_nlink)


def _acl(fd, name="system.posix_acl_access"):
    try:
        return os.getxattr(fd, name)
    except OSError as error:
        if error.errno in (errno.ENODATA, errno.ENOTSUP):
            return None
        raise


def _protections(fd):
    info = os.fstat(fd)
    try:
        names = os.listxattr(fd)
    except OSError as error:
        if error.errno != errno.ENOTSUP:
            raise
        names = []
    if any(name.startswith("system.") and name != "system.posix_acl_access"
           for name in names):
        raise OSError(errno.ENOTSUP, "unrecognized filesystem access metadata")
    labels = {name: os.getxattr(fd, name) for name in names
              if name.startswith("security.")}
    return stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid, _acl(fd), labels


def _private(fd, mode=0o600):
    info = os.fstat(fd)
    if info.st_uid != os.geteuid():
        os.fchown(fd, os.geteuid(), -1)
    names = ["system.posix_acl_access"]
    if stat.S_ISDIR(info.st_mode):
        names.append("system.posix_acl_default")
    for name in names:
        if _acl(fd, name) is not None:
            os.removexattr(fd, name)
    if stat.S_IMODE(os.fstat(fd).st_mode) != mode:
        os.fchmod(fd, mode)
    actual_mode, uid, _, acl, _ = _protections(fd)
    if uid != os.geteuid() or actual_mode != mode or acl is not None:
        raise OSError(errno.ENOTSUP, "private recovery permissions could not be verified")


def _apply(fd, protections):
    mode, uid, gid, acl, labels = protections
    if mode & (stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX):
        raise OSError(errno.ENOTSUP, "replacement of special-mode files is not supported")
    info = os.fstat(fd)
    if (info.st_uid, info.st_gid) != (uid, gid):
        os.fchown(fd, uid, gid)
    if _acl(fd) is not None:
        os.removexattr(fd, "system.posix_acl_access")
    os.fchmod(fd, mode)
    if acl is not None:
        os.setxattr(fd, "system.posix_acl_access", acl)
    if _protections(fd) != protections:
        raise OSError(errno.ENOTSUP, "destination ownership, permissions, ACL, or security "
                      "labels could not be preserved")


def _close(candidate):
    fd, candidate.fd = candidate.fd, None
    if fd is not None:
        try:
            os.close(fd)
        except BaseException:
            candidate.close_failed = True
            raise
    candidate.complete = candidate.written and not candidate.close_failed


def _stage(data, directory, candidate):
    candidate.directory = tempfile.mkdtemp(prefix=".yapyon-", dir=directory)
    candidate.directory_identity = _identity(os.stat(candidate.directory, follow_symlinks=False))
    candidate.directory_fd = os.open(candidate.directory, os.O_RDONLY | os.O_DIRECTORY
                                     | os.O_NOFOLLOW | os.O_CLOEXEC)
    if _identity(os.fstat(candidate.directory_fd)) != candidate.directory_identity:
        raise OSError(errno.EBUSY, "staging directory changed", candidate.directory)
    _private(candidate.directory_fd, 0o700)
    candidate.path = os.path.join(candidate.directory, "record.yap")
    candidate.fd = os.open("record.yap", os.O_WRONLY | os.O_CREAT | os.O_EXCL
                           | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600,
                           dir_fd=candidate.directory_fd)
    candidate.identity = _identity(os.fstat(candidate.fd))
    _private(candidate.fd)
    remaining = memoryview(data)
    while remaining:
        count = os.write(candidate.fd, remaining)
        if count <= 0:
            raise OSError(errno.EIO, "staging write made no progress", candidate.path)
        remaining = remaining[count:]
    candidate.written = True


def _same_path(candidate):
    return (_identity(os.stat(candidate.directory, follow_symlinks=False))
            == candidate.directory_identity
            and _identity(os.stat(candidate.path, follow_symlinks=False)) == candidate.identity)


def _quiet_close(fd, error):
    if fd is not None:
        try:
            os.close(fd)
        except BaseException as cleanup:
            error.add_note(f"Descriptor cleanup also failed: {cleanup!r}")


def _retain(candidate, error):
    if candidate.path is None:
        return False
    private = False
    try:
        if candidate.fd is None:
            candidate.fd = os.open("record.yap", os.O_RDONLY | os.O_NOFOLLOW
                                   | os.O_NONBLOCK | os.O_CLOEXEC,
                                   dir_fd=candidate.directory_fd)
        if _identity(os.fstat(candidate.fd)) != candidate.identity:
            raise OSError(errno.EBUSY, "staging pathname changed", candidate.path)
        _private(candidate.directory_fd, 0o700)
        _private(candidate.fd)
        private = True
    except BaseException as recovery:
        error.add_note(f"Could not verify private recovery at {candidate.path!r}: {recovery!r}")
    finally:
        try:
            _close(candidate)
        except BaseException as cleanup:
            error.add_note(f"Recovery close failed at {candidate.path!r}: {cleanup!r}")
    try:
        return private and _same_path(candidate)
    except BaseException as recovery:
        error.add_note(f"Recovery pathname unavailable at {candidate.path!r}: {recovery!r}")
        return False


def _remove_directory(candidate):
    if candidate.directory is None:
        return
    location = (os.path.basename(candidate.directory) if candidate.parent_fd is not None
                else candidate.directory)
    info = os.stat(location, dir_fd=candidate.parent_fd, follow_symlinks=False)
    if _identity(info) != candidate.directory_identity:
        raise OSError(errno.EBUSY, "staging directory changed", candidate.directory)
    os.rmdir(location, dir_fd=candidate.parent_fd)


def _discard(candidate, error):
    try:
        if candidate.path is not None:
            try:
                info = os.stat("record.yap", dir_fd=candidate.directory_fd,
                               follow_symlinks=False)
            except FileNotFoundError:
                info = None
            if info is not None:
                if _identity(info) != candidate.identity:
                    raise OSError(errno.EBUSY, "staging pathname changed", candidate.path)
                os.unlink("record.yap", dir_fd=candidate.directory_fd)
        _remove_directory(candidate)
    except BaseException as cleanup:
        error.add_note(f"Additional staging data may remain at {candidate.directory!r}; "
                       f"cleanup failed: {cleanup!r}")


def _recover(candidate, data, error):
    retained = _retain(candidate, error)
    if retained and candidate.complete:
        return candidate
    if not isinstance(error, OSError):
        return candidate if retained else _Candidate()
    fallback = _Candidate()
    fallback_retained = False
    try:
        try:
            _stage(data, None, fallback)
            _close(fallback)
        except BaseException as recovery:
            error.add_note(f"Fallback recovery failed at {fallback.path!r}: {recovery!r}; "
                           "its contents are not confirmed complete")
        fallback_retained = _retain(fallback, error)
        if fallback_retained and fallback.complete:
            _discard(candidate, error)
            return fallback
        if retained:
            if fallback_retained:
                error.add_note(f"Additional incomplete recovery retained at {fallback.path!r}")
            else:
                _discard(fallback, error)
            return candidate
        if fallback_retained:
            error.add_note(f"Original staging data may remain at {candidate.directory!r}")
            return fallback
        for item in (candidate, fallback):
            if item.path is not None:
                error.add_note(f"Staging data may remain at {item.path!r}; "
                               "privacy, accessibility, and completeness are unverified")
        return _Candidate()
    finally:
        _quiet_close(fallback.fd, error)
        fallback.fd = None
        _quiet_close(fallback.directory_fd, error)
        fallback.directory_fd = None


def _resolve(path):
    try:
        return os.path.realpath(path, strict=True)
    except FileNotFoundError:
        return os.path.realpath(path)


def _outcome(destination, candidate, started, replaced):
    if replaced:
        return "Replacement completed."
    if not started:
        return "Replacement was not attempted."
    try:
        current = os.stat(destination, follow_symlinks=False)
        if _identity(current) == candidate.identity:
            return "Replacement may have completed: destination currently refers to the staged inode."
    except BaseException:
        return "Replacement outcome is uncertain; destination could not be inspected."
    return "Replacement outcome is uncertain; destination does not currently identify the staged inode."


def write_file(text: str, path) -> None:
    """Replace a resolved regular-file target after complete UTF-8 staging.

    A verified owner-only directory protects the candidate until publication.
    Existing Linux ownership, modes, POSIX access ACLs, and security labels must
    match; special modes are refused. Failures retain native identity and carry
    recovery_path and outcome notes. No power-loss durability is promised.
    """
    path = os.fspath(path)
    if not isinstance(path, str):
        raise TypeError("path must be a string or an os.PathLike returning str")
    data = str.encode(text, "utf-8")
    destination = os.path.abspath(path)
    directory_fd = original_fd = None
    candidate = _Candidate()
    operation, error = "resolve destination", None
    started = replaced = False
    try:
        if sys.platform != "linux":
            raise OSError(errno.ENOTSUP, "verified safe-file protections require Linux", path)
        destination = _resolve(path)
        directory, name = os.path.split(destination)
        operation = "open target directory"
        directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        operation = "inspect destination"
        try:
            before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            before = None
        protections = None
        if before is not None:
            if stat.S_ISDIR(before.st_mode):
                raise IsADirectoryError(errno.EISDIR, "destination is a directory", destination)
            if not stat.S_ISREG(before.st_mode):
                raise OSError(errno.EINVAL, "destination must be a regular file", destination)
            original_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                                  | os.O_CLOEXEC, dir_fd=directory_fd)
            protections = _protections(original_fd)
            if _signature(os.fstat(original_fd)) != _signature(before):
                raise OSError(errno.EBUSY, "destination changed during inspection", destination)
        operation = "create/write staging file"
        candidate.parent_fd = directory_fd
        _stage(data, directory, candidate)
        operation = "preserve destination protections"
        if protections is not None:
            _apply(candidate.fd, protections)
        staged = os.fstat(candidate.fd)
        operation = "close staging file"
        _close(candidate)
        operation = "check destination for concurrent changes"
        if (_resolve(path) != destination
                or _identity(os.stat(directory)) != _identity(os.fstat(directory_fd))
                or not _same_path(candidate)):
            raise OSError(errno.EBUSY, "destination or staging path changed before replacement", destination)
        mode, uid, _, acl, _ = _protections(candidate.directory_fd)
        if mode != 0o700 or uid != os.geteuid() or acl is not None:
            raise OSError(errno.EBUSY, "staging directory protections changed", candidate.directory)
        try:
            current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            current = None
        if ((None if current is None else _signature(current))
                != (None if before is None else _signature(before))):
            raise OSError(errno.EBUSY, "destination changed before replacement", destination)
        if original_fd is not None and _protections(original_fd) != protections:
            raise OSError(errno.EBUSY, "destination protections changed", destination)
        staged_now = os.stat("record.yap", dir_fd=candidate.directory_fd, follow_symlinks=False)
        if _signature(staged_now) != _signature(staged):
            candidate.written = candidate.complete = False
            raise OSError(errno.EBUSY, "staging file changed before replacement", candidate.path)
        operation = "replace destination"
        started = True
        os.replace("record.yap", name, src_dir_fd=candidate.directory_fd, dst_dir_fd=directory_fd)
        replaced = True
        operation = "remove empty staging directory"
        _remove_directory(candidate)
    except BaseException as failure:
        error = failure
        outcome = _outcome(destination, candidate, started, replaced)
        recovery = (_recover(candidate, data, error) if sys.platform == "linux" else _Candidate())
        error.recovery_path = recovery.path
        state = ("complete UTF-8 replacement" if recovery.complete else
                 "contents not confirmed complete")
        retained = (f"retained at {recovery.path!r} ({state})" if recovery.path else
                    "no verified accessible recovery file is available")
        error.add_note(f"Safe-file destination {destination!r}: {operation} failed; {retained}. {outcome}")
        raise
    finally:
        cleanup_error = None
        descriptors = (candidate.fd, original_fd, candidate.directory_fd, directory_fd)
        candidate.fd = candidate.directory_fd = None
        for fd in descriptors:
            if error is not None:
                _quiet_close(fd, error)
            elif fd is not None:
                try:
                    os.close(fd)
                except BaseException as cleanup:
                    cleanup.recovery_path = None
                    cleanup.add_note(f"Safe-file destination {destination!r}: descriptor cleanup "
                                     f"failed; replacement {'completed' if replaced else 'did not complete'}.")
                    error = cleanup_error = cleanup
        if cleanup_error is not None:
            raise cleanup_error
