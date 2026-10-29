"""Safe path export: checked replacement, access controls, and recovery."""

import errno
import os
from pathlib import Path
import stat
import struct
import sys

import pytest

import yapyon
from yapyon import _safe


pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="verified Linux file protections")


@pytest.fixture(autouse=True)
def private_fallback_directory(tmp_path_factory, monkeypatch):
    directory = tmp_path_factory.mktemp("dump-safe-fallback")
    directory.chmod(0o700)
    monkeypatch.setattr(_safe.tempfile, "tempdir", str(directory))
    return directory


def _mode(path):
    return stat.S_IMODE(path.stat().st_mode)


def _notes(error):
    return "\n".join(error.__notes__)


def _recovery(error, value):
    path = Path(error.recovery_path)
    assert path.is_file()
    assert _mode(path) == 0o600
    assert path.stat().st_uid == os.geteuid()
    assert _mode(path.parent) == 0o700
    assert path.parent.stat().st_uid == os.geteuid()
    assert path.read_text(encoding="utf-8") == yapyon.dumps(value)
    assert str(path) in _notes(error)
    assert "complete UTF-8 replacement" in _notes(error)
    return path


def _access_acl(*, private=False):
    named_uid = os.geteuid() ^ 1
    entries = [(1, 6 if private else 7, 0xFFFFFFFF), (2, 4, named_uid),
               (4, 4 if private else 7, 0xFFFFFFFF),
               (16, 4 if private else 7, 0xFFFFFFFF),
               (32, 0 if private else 7, 0xFFFFFFFF)]
    return struct.pack("<I", 2) + b"".join(struct.pack("<HHI", *entry) for entry in entries)


def test_new_destination_is_complete_utf8_and_private_even_with_open_umask(tmp_path):
    destination = tmp_path / "new.yap"
    value = {"name": "café ガイド", "nested": [1, None, True]}
    previous = os.umask(0)
    try:
        assert yapyon.dump_safe(value, destination) is None
    finally:
        os.umask(previous)
    assert destination.read_bytes() == yapyon.dumps(value).encode("utf-8")
    assert yapyon.loads_record(destination.read_text(encoding="utf-8")) == value
    assert _mode(destination) == 0o600
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.parametrize("mode", [0o400, 0o600, 0o640, 0o644, 0o660, 0o755])
def test_existing_destination_keeps_actual_mode_and_ownership(tmp_path, mode):
    destination = tmp_path / "existing.yap"
    destination.write_text("old bytes", encoding="utf-8")
    destination.chmod(mode)
    before = destination.stat()
    yapyon.dump_safe({"new": 42}, str(destination))
    after = destination.stat()
    assert (after.st_uid, after.st_gid) == (before.st_uid, before.st_gid)
    assert stat.S_IMODE(after.st_mode) == mode
    assert after.st_ino != before.st_ino
    assert destination.read_text(encoding="utf-8") == "new: 42\n"


def test_pathlike_is_accepted_without_arbitrary_string_conversion(tmp_path):
    destination = tmp_path / "pathlike.yap"

    class FilePath:
        def __fspath__(self):
            return str(destination)

        def __str__(self):
            raise AssertionError("arbitrary conversion was called")

    yapyon.dump_safe(1, FilePath())
    assert destination.read_bytes() == b"1\n"


def test_bytes_paths_are_explicitly_refused_without_staging(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("staging must not happen")

    monkeypatch.setattr(_safe.tempfile, "mkdtemp", forbidden)
    with pytest.raises(TypeError, match="path"):
        yapyon.dump_safe(1, os.fsencode(tmp_path / "bytes.yap"))
    assert list(tmp_path.iterdir()) == []


def test_existing_symlink_and_parent_symlink_chains_are_preserved(tmp_path):
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    destination = profiles / "prod.yap"
    destination.write_text("old", encoding="utf-8")
    alias = tmp_path / "alias"
    alias.symlink_to("profiles", target_is_directory=True)
    intermediate = profiles / "current.yap"
    intermediate.symlink_to("prod.yap")
    public = tmp_path / "public.yap"
    public.symlink_to("alias/current.yap")
    yapyon.dump_safe({"name": "new"}, public)
    assert destination.read_bytes() == b'name: "new"\n'
    assert public.readlink() == Path("alias/current.yap")
    assert intermediate.readlink() == Path("prod.yap")
    assert alias.readlink() == Path("profiles")


def test_dangling_destination_symlink_creates_selected_target(tmp_path):
    (tmp_path / "profiles").mkdir()
    public = tmp_path / "current.yap"
    public.symlink_to("profiles/new.yap")
    yapyon.dump_safe([1, 2], public)
    assert public.is_symlink()
    assert (tmp_path / "profiles/new.yap").read_bytes() == b"[1, 2]\n"
    assert _mode(public) == 0o600


def test_replace_failure_keeps_original_and_private_complete_new_data(tmp_path, monkeypatch, capsys):
    destination = tmp_path / "original.yap"
    destination.write_bytes(b"original bytes")
    destination.chmod(0o644)
    before = destination.stat()
    failure = PermissionError(errno.EACCES, "replacement denied", str(destination))

    def denied(*args, **kwargs):
        raise failure

    monkeypatch.setattr(_safe.os, "replace", denied)
    with pytest.raises(PermissionError) as caught:
        yapyon.dump_safe({"new": "é"}, destination)
    assert caught.value is failure
    assert destination.read_bytes() == b"original bytes"
    assert destination.stat().st_ino == before.st_ino
    assert _mode(destination) == 0o644
    recovery = _recovery(failure, {"new": "é"})
    assert recovery.parent.parent == tmp_path
    assert str(destination) in _notes(failure)
    assert "replace destination failed" in _notes(failure)
    assert capsys.readouterr() == ("", "")


def test_symlink_failure_reports_actual_target_and_retains_link(tmp_path, monkeypatch):
    destination = tmp_path / "actual.yap"
    destination.write_bytes(b"old")
    link = tmp_path / "public.yap"
    link.symlink_to("actual.yap")
    failure = OSError(errno.EXDEV, "cannot replace")

    def denied(*args, **kwargs):
        raise failure

    monkeypatch.setattr(_safe.os, "replace", denied)
    with pytest.raises(OSError) as caught:
        yapyon.dump_safe(42, link)
    assert caught.value is failure
    assert link.is_symlink()
    assert destination.read_bytes() == b"old"
    assert str(destination) in _notes(failure)
    _recovery(failure, 42)


@pytest.mark.parametrize("value, options, error", [
    ({"bad": object()}, {}, TypeError),
    ({"text": "too large"}, {"max_size": 1}, ValueError),
    ([[1]], {"max_depth": 1}, ValueError),
    (1, {"max_size": False}, TypeError),
])
def test_validation_failure_has_no_destination_or_staging_effects(tmp_path, monkeypatch, value, options, error):
    destination = tmp_path / "existing.yap"
    destination.write_bytes(b"old")
    before = destination.stat()

    def forbidden(*args, **kwargs):
        raise AssertionError("validation must finish before staging")

    monkeypatch.setattr(_safe.tempfile, "mkdtemp", forbidden)
    with pytest.raises(error):
        yapyon.dump_safe(value, destination, **options)
    assert destination.read_bytes() == b"old"
    assert destination.stat().st_ino == before.st_ino
    assert list(tmp_path.iterdir()) == [destination]


def test_callback_failure_is_not_relabeled_as_filesystem_failure(tmp_path):
    failure = RuntimeError("callback failed")
    destination = tmp_path / "new.yap"

    def warn(message):
        raise failure

    with pytest.raises(RuntimeError) as caught:
        yapyon.dump_safe(10 ** 4300, destination, warn=warn)
    assert caught.value is failure
    assert not hasattr(failure, "recovery_path")
    assert list(tmp_path.iterdir()) == []


def test_unavailable_target_staging_retains_private_fallback_and_original_error(tmp_path, monkeypatch):
    directory = tmp_path / "target"
    directory.mkdir()
    fallback = tmp_path / "fallback"
    fallback.mkdir()
    destination = directory / "existing.yap"
    destination.write_bytes(b"old")
    failure = PermissionError(errno.EACCES, "target staging denied", str(directory))
    original = _safe.tempfile.mkdtemp

    def staging(*args, **kwargs):
        if kwargs.get("dir") == str(directory):
            raise failure
        return original(*args, **kwargs)

    monkeypatch.setattr(_safe.tempfile, "tempdir", str(fallback))
    monkeypatch.setattr(_safe.tempfile, "mkdtemp", staging)
    with pytest.raises(PermissionError) as caught:
        yapyon.dump_safe({"complete": True}, destination)
    assert caught.value is failure
    assert destination.read_bytes() == b"old"
    assert _recovery(failure, {"complete": True}).parent.parent == fallback
    assert list(directory.iterdir()) == [destination]


def test_failed_target_and_fallback_creation_report_no_recovery(tmp_path, monkeypatch):
    destination = tmp_path / "new.yap"
    failure = PermissionError(errno.EACCES, "no staging")
    fallback_failure = OSError(errno.ENOSPC, "no fallback space")
    calls = []

    def denied(*args, **kwargs):
        calls.append(kwargs.get("dir"))
        raise failure if len(calls) == 1 else fallback_failure

    monkeypatch.setattr(_safe.tempfile, "mkdtemp", denied)
    with pytest.raises(PermissionError) as caught:
        yapyon.dump_safe(1, destination)
    assert caught.value is failure
    assert failure.recovery_path is None
    assert len(calls) == 2
    assert "Fallback recovery failed" in _notes(failure)
    assert "no verified accessible recovery file" in _notes(failure)
    assert not destination.exists()


def test_partial_staging_write_is_never_reported_complete(tmp_path, monkeypatch):
    destination = tmp_path / "original.yap"
    destination.write_bytes(b"old")
    original = _safe.os.write
    failure = OSError(errno.ENOSPC, "write failed")
    calls = []

    def partial(fd, data):
        calls.append(fd)
        if len(calls) == 1:
            return original(fd, data[:2])
        raise failure

    monkeypatch.setattr(_safe.os, "write", partial)
    with pytest.raises(OSError) as caught:
        yapyon.dump_safe({"new": "value"}, destination)
    assert caught.value is failure
    recovery = Path(failure.recovery_path)
    assert recovery.read_bytes() == yapyon.dumps({"new": "value"}).encode("utf-8")[:2]
    assert _mode(recovery) == 0o600
    assert "contents not confirmed complete" in _notes(failure)
    assert "complete UTF-8 replacement" not in _notes(failure)
    assert destination.read_bytes() == b"old"


def test_zero_progress_write_refuses_replacement(tmp_path, monkeypatch):
    destination = tmp_path / "new.yap"
    monkeypatch.setattr(_safe.os, "write", lambda fd, data: 0)
    with pytest.raises(OSError) as caught:
        yapyon.dump_safe(1, destination)
    assert caught.value.errno == errno.EIO
    assert Path(caught.value.recovery_path).read_bytes() == b""
    assert "not confirmed complete" in _notes(caught.value)
    assert not destination.exists()


def test_staging_close_failure_preserves_original_and_native_error(tmp_path, monkeypatch):
    destination = tmp_path / "existing.yap"
    destination.write_bytes(b"old")
    original = _safe.os.close
    failure = OSError(errno.EIO, "close failed")
    calls = []

    def close(fd):
        calls.append(fd)
        original(fd)
        if len(calls) == 1:
            raise failure

    monkeypatch.setattr(_safe.os, "close", close)
    with pytest.raises(OSError) as caught:
        yapyon.dump_safe(42, destination)
    assert caught.value is failure
    assert destination.read_bytes() == b"old"
    _recovery(failure, 42)
    assert "close staging file failed" in _notes(failure)
    assert "complete UTF-8 replacement" in _notes(failure)


def test_metadata_failure_is_native_and_original_protections_survive(tmp_path, monkeypatch):
    destination = tmp_path / "original.yap"
    destination.write_bytes(b"old")
    destination.chmod(0o640)
    failure = PermissionError(errno.EPERM, "chmod denied")

    def denied(*args, **kwargs):
        raise failure

    monkeypatch.setattr(_safe.os, "fchmod", denied)
    with pytest.raises(PermissionError) as caught:
        yapyon.dump_safe(42, destination)
    assert caught.value is failure
    assert destination.read_bytes() == b"old"
    assert _mode(destination) == 0o640
    _recovery(failure, 42)
    assert "preserve destination protections failed" in _notes(failure)


def test_linux_access_acl_is_preserved_byte_for_byte(tmp_path):
    destination = tmp_path / "acl.yap"
    destination.write_bytes(b"old")
    os.setxattr(destination, "system.posix_acl_access", _access_acl(private=True))
    before = os.getxattr(destination, "system.posix_acl_access")
    mode = _mode(destination)
    yapyon.dump_safe({"new": True}, destination)
    assert os.getxattr(destination, "system.posix_acl_access") == before
    assert _mode(destination) == mode
    assert destination.read_bytes() == b"new: True\n"


def test_inherited_default_acl_cannot_broaden_new_file_access(tmp_path):
    os.setxattr(tmp_path, "system.posix_acl_default", _access_acl())
    destination = tmp_path / "new.yap"
    yapyon.dump_safe(1, destination)
    assert _mode(destination) == 0o600
    with pytest.raises(OSError) as caught:
        os.getxattr(destination, "system.posix_acl_access")
    assert caught.value.errno == errno.ENODATA


def test_failed_replace_restores_private_mode_and_removes_access_acl(tmp_path, monkeypatch):
    destination = tmp_path / "acl.yap"
    destination.write_bytes(b"old")
    os.setxattr(destination, "system.posix_acl_access", _access_acl(private=True))
    before = os.getxattr(destination, "system.posix_acl_access")

    def denied(*args, **kwargs):
        raise OSError(errno.EACCES, "replace denied")

    monkeypatch.setattr(_safe.os, "replace", denied)
    with pytest.raises(OSError) as caught:
        yapyon.dump_safe(42, destination)
    recovery = _recovery(caught.value, 42)
    with pytest.raises(OSError) as missing:
        os.getxattr(recovery, "system.posix_acl_access")
    assert missing.value.errno == errno.ENODATA
    assert os.getxattr(destination, "system.posix_acl_access") == before


def test_failed_acl_copy_keeps_original_and_retains_complete_recovery(tmp_path, monkeypatch):
    destination = tmp_path / "acl.yap"
    destination.write_bytes(b"old")
    os.setxattr(destination, "system.posix_acl_access", _access_acl(private=True))
    before = os.getxattr(destination, "system.posix_acl_access")
    failure = OSError(errno.ENOTSUP, "ACL setting unavailable")

    def denied(*args, **kwargs):
        raise failure

    monkeypatch.setattr(_safe.os, "setxattr", denied)
    with pytest.raises(OSError) as caught:
        yapyon.dump_safe(1, destination)
    assert caught.value is failure
    assert destination.read_bytes() == b"old"
    assert os.getxattr(destination, "system.posix_acl_access") == before
    _recovery(failure, 1)


def test_ownership_preservation_is_verified_not_assumed_after_chown(tmp_path, monkeypatch):
    destination = tmp_path / "ownership.yap"
    destination.write_bytes(b"old")
    original = _safe._protections
    inode = destination.stat().st_ino
    changes = []

    def protections(fd):
        mode, uid, gid, acl, labels = original(fd)
        if os.fstat(fd).st_ino == inode:
            uid ^= 1
        return mode, uid, gid, acl, labels

    monkeypatch.setattr(_safe, "_protections", protections)
    monkeypatch.setattr(_safe.os, "fchown", lambda fd, uid, gid: changes.append((uid, gid)))
    with pytest.raises(OSError) as caught:
        yapyon.dump_safe(1, destination)
    assert caught.value.errno == errno.ENOTSUP
    assert changes
    assert destination.read_bytes() == b"old"
    _recovery(caught.value, 1)


def test_security_label_mismatch_is_refused_without_changing_original(tmp_path, monkeypatch):
    destination = tmp_path / "labeled.yap"
    destination.write_bytes(b"old")
    inode = destination.stat().st_ino
    original = _safe._protections

    def protections(fd):
        mode, uid, gid, acl, labels = original(fd)
        if os.fstat(fd).st_ino == inode:
            labels = {"security.selinux": b"different-label"}
        return mode, uid, gid, acl, labels

    monkeypatch.setattr(_safe, "_protections", protections)
    with pytest.raises(OSError) as caught:
        yapyon.dump_safe(1, destination)
    assert caught.value.errno == errno.ENOTSUP
    assert destination.read_bytes() == b"old"
    _recovery(caught.value, 1)


@pytest.mark.parametrize("special", [stat.S_ISUID, stat.S_ISGID, stat.S_ISVTX])
def test_special_mode_targets_are_refused_with_private_recovery(tmp_path, special):
    destination = tmp_path / "special.yap"
    destination.write_bytes(b"old")
    destination.chmod(0o600 | special)
    with pytest.raises(OSError) as caught:
        yapyon.dump_safe(1, destination)
    assert caught.value.errno == errno.ENOTSUP
    assert destination.read_bytes() == b"old"
    assert _mode(destination) == 0o600 | special
    _recovery(caught.value, 1)


@pytest.mark.parametrize("kind", ["directory", "fifo"])
def test_nonregular_targets_are_refused_without_opening_or_blocking(tmp_path, monkeypatch, kind):
    destination = tmp_path / "target"
    if kind == "directory":
        destination.mkdir()
        (destination / "sentinel").write_bytes(b"old")
    else:
        os.mkfifo(destination)
    original = _safe.os.open
    opened = []

    def opening(path, flags, *args, **kwargs):
        opened.append((os.fspath(path), flags))
        assert os.fspath(path) != destination.name
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(_safe.tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(_safe.os, "open", opening)
    with pytest.raises(OSError) as caught:
        yapyon.dump_safe(1, destination)
    assert caught.value.errno == (errno.EISDIR if kind == "directory" else errno.EINVAL)
    assert stat.S_ISDIR(destination.stat().st_mode) if kind == "directory" else stat.S_ISFIFO(destination.stat().st_mode)
    _recovery(caught.value, 1)


def test_symlink_loop_keeps_native_loop_error_with_recovery(tmp_path, monkeypatch):
    first, second = tmp_path / "first", tmp_path / "second"
    first.symlink_to("second")
    second.symlink_to("first")
    monkeypatch.setattr(_safe.tempfile, "tempdir", str(tmp_path))
    with pytest.raises(OSError) as caught:
        yapyon.dump_safe(1, first)
    assert caught.value.errno == errno.ELOOP
    assert first.is_symlink() and second.is_symlink()
    _recovery(caught.value, 1)


@pytest.mark.parametrize("change", ["contents", "permissions", "inode", "newly-created"])
def test_destination_conflicts_before_replace_are_not_overwritten(tmp_path, monkeypatch, change):
    destination = tmp_path / "conflict.yap"
    if change != "newly-created":
        destination.write_bytes(b"old")
    original = _safe._close
    changed = []

    def closing(candidate):
        original(candidate)
        if not changed:
            changed.append(True)
            if change == "permissions":
                destination.chmod(0o400)
            elif change == "inode":
                other = tmp_path / "other.yap"
                other.write_bytes(b"concurrent replacement")
                os.replace(other, destination)
            else:
                destination.write_bytes(b"concurrent data")

    monkeypatch.setattr(_safe, "_close", closing)
    with pytest.raises(OSError) as caught:
        yapyon.dump_safe(42, destination)
    assert caught.value.errno == errno.EBUSY
    assert destination.read_bytes() == (b"old" if change == "permissions" else
                                        b"concurrent replacement" if change == "inode" else
                                        b"concurrent data")
    _recovery(caught.value, 42)


def test_retargeted_symlink_is_detected_before_replacement(tmp_path, monkeypatch):
    first, second = tmp_path / "first.yap", tmp_path / "second.yap"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    link = tmp_path / "link.yap"
    link.symlink_to("first.yap")
    original = _safe._close
    changed = []

    def closing(candidate):
        original(candidate)
        if not changed:
            changed.append(True)
            link.unlink()
            link.symlink_to("second.yap")

    monkeypatch.setattr(_safe, "_close", closing)
    with pytest.raises(OSError) as caught:
        yapyon.dump_safe(42, link)
    assert caught.value.errno == errno.EBUSY
    assert first.read_bytes() == b"first"
    assert second.read_bytes() == b"second"
    assert link.readlink() == Path("second.yap")
    _recovery(caught.value, 42)


def test_cleanup_close_error_does_not_mask_replace_failure(tmp_path, monkeypatch):
    destination = tmp_path / "existing.yap"
    destination.write_bytes(b"old")
    failure = OSError(errno.EXDEV, "replace failed")
    cleanup = OSError(errno.EIO, "cleanup failed")
    original = _safe.os.close
    calls = []

    def denied(*args, **kwargs):
        raise failure

    def close(fd):
        calls.append(fd)
        original(fd)
        if len(calls) == 3:
            raise cleanup

    monkeypatch.setattr(_safe.os, "replace", denied)
    monkeypatch.setattr(_safe.os, "close", close)
    with pytest.raises(OSError) as caught:
        yapyon.dump_safe(42, destination)
    assert caught.value is failure
    assert "Descriptor cleanup also failed" in _notes(failure)
    _recovery(failure, 42)
    assert destination.read_bytes() == b"old"


def test_short_filesystem_writes_are_completed_before_replacement(tmp_path, monkeypatch):
    destination = tmp_path / "short-writes.yap"
    original = _safe.os.write
    calls = []

    def short(fd, data):
        calls.append(len(data))
        return original(fd, data[:2])

    monkeypatch.setattr(_safe.os, "write", short)
    yapyon.dump_safe({"value": "complete"}, destination)
    assert len(calls) > 1
    assert destination.read_bytes() == b'value: "complete"\n'


def test_missing_dangling_target_parent_retains_fallback_and_names_target(tmp_path, monkeypatch):
    link = tmp_path / "dangling.yap"
    link.symlink_to("missing/target.yap")
    monkeypatch.setattr(_safe.tempfile, "tempdir", str(tmp_path))
    with pytest.raises(FileNotFoundError) as caught:
        yapyon.dump_safe(42, link)
    assert link.is_symlink()
    assert not (tmp_path / "missing").exists()
    assert str(tmp_path / "missing/target.yap") in _notes(caught.value)
    _recovery(caught.value, 42)


def test_changed_staging_content_is_not_claimed_as_complete_output(tmp_path, monkeypatch):
    destination = tmp_path / "existing.yap"
    destination.write_bytes(b"old")
    original = _safe._close
    changed = []

    def closing(candidate):
        original(candidate)
        if not changed:
            changed.append(True)
            Path(candidate.path).write_bytes(b"changed")

    monkeypatch.setattr(_safe, "_close", closing)
    with pytest.raises(OSError) as caught:
        yapyon.dump_safe(42, destination)
    assert caught.value.errno == errno.EBUSY
    assert destination.read_bytes() == b"old"
    _recovery(caught.value, 42)
    assert "complete UTF-8 replacement" in _notes(caught.value)


def test_renamed_parent_does_not_leave_nonprivate_staging_behind(tmp_path, monkeypatch):
    directory = tmp_path / "parent"
    directory.mkdir()
    moved = tmp_path / "moved"
    fallback = tmp_path / "fallback"
    fallback.mkdir()
    destination = directory / "existing.yap"
    destination.write_bytes(b"old")
    destination.chmod(0o644)
    original = _safe._close
    changed = []

    def closing(candidate):
        original(candidate)
        if not changed:
            changed.append(True)
            directory.rename(moved)

    monkeypatch.setattr(_safe, "_close", closing)
    monkeypatch.setattr(_safe.tempfile, "tempdir", str(fallback))
    with pytest.raises(OSError) as caught:
        yapyon.dump_safe(42, destination)
    assert (moved / "existing.yap").read_bytes() == b"old"
    assert list(moved.iterdir()) == [moved / "existing.yap"]
    assert _recovery(caught.value, 42).parent.parent == fallback


def test_auxiliary_close_failure_reports_already_completed_replacement(tmp_path, monkeypatch):
    destination = tmp_path / "existing.yap"
    destination.write_bytes(b"old")
    original = _safe.os.close
    failure = OSError(errno.EIO, "descriptor close failed")
    calls = []

    def close(fd):
        calls.append(fd)
        original(fd)
        if len(calls) == 2:
            raise failure

    monkeypatch.setattr(_safe.os, "close", close)
    with pytest.raises(OSError) as caught:
        yapyon.dump_safe(42, destination)
    assert caught.value is failure
    assert failure.recovery_path is None
    assert "replacement completed" in _notes(failure)
    assert len(calls) == 4
    assert destination.read_bytes() == b"42\n"


@pytest.mark.parametrize("with_acl", [False, True])
def test_final_permissions_are_only_applied_inside_private_staging_directory(tmp_path, monkeypatch, with_acl):
    tmp_path.chmod(0o755)
    destination = tmp_path / "publicly-readable.yap"
    destination.write_bytes(b"old")
    destination.chmod(0o644)
    if with_acl:
        os.setxattr(destination, "system.posix_acl_access", _access_acl(private=True))
    final_mode = _mode(destination)
    original_apply, original_replace = _safe._apply, _safe.os.replace
    staged_directories = []

    def apply(fd, protections):
        candidate = Path(os.readlink(f"/proc/self/fd/{fd}"))
        staged_directories.append(candidate.parent)
        assert _mode(candidate) == 0o600
        assert _mode(candidate.parent) == 0o700
        assert candidate.parent.stat().st_uid == os.geteuid()
        original_apply(fd, protections)
        assert _mode(candidate) == final_mode
        assert _mode(candidate.parent) == 0o700

    def replace(source, target, *, src_dir_fd, dst_dir_fd):
        assert src_dir_fd != dst_dir_fd
        assert stat.S_IMODE(os.fstat(src_dir_fd).st_mode) == 0o700
        assert stat.S_IMODE(os.stat(source, dir_fd=src_dir_fd).st_mode) == final_mode
        return original_replace(source, target, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)

    monkeypatch.setattr(_safe, "_apply", apply)
    monkeypatch.setattr(_safe.os, "replace", replace)
    yapyon.dump_safe({"new": True}, destination)
    assert destination.read_bytes() == b"new: True\n"
    assert _mode(destination) == final_mode
    assert staged_directories and not staged_directories[0].exists()
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.parametrize("phase", ["write", "metadata"])
@pytest.mark.parametrize("exception_type", [KeyboardInterrupt, RuntimeError])
def test_interruption_closes_all_owned_descriptors_without_heavy_retry(
        tmp_path, monkeypatch, private_fallback_directory, phase, exception_type):
    destination = tmp_path / "existing.yap"
    destination.write_bytes(b"old")
    destination.chmod(0o644)
    failure = exception_type("interrupted")
    original_open, original_close = _safe.os.open, _safe.os.close
    original_write, original_apply = _safe.os.write, _safe._apply
    owned, writes = set(), []
    value = {"new": 42}

    def opening(*args, **kwargs):
        fd = original_open(*args, **kwargs)
        owned.add(fd)
        return fd

    def closing(fd):
        try:
            return original_close(fd)
        finally:
            owned.discard(fd)

    def writing(fd, data):
        writes.append(fd)
        original_write(fd, data[:2])
        raise failure

    def applying(fd, protections):
        original_apply(fd, protections)
        raise failure

    monkeypatch.setattr(_safe.os, "open", opening)
    monkeypatch.setattr(_safe.os, "close", closing)
    if phase == "write":
        monkeypatch.setattr(_safe.os, "write", writing)
    else:
        monkeypatch.setattr(_safe, "_apply", applying)
    with pytest.raises(exception_type) as caught:
        yapyon.dump_safe(value, destination)
    assert caught.value is failure
    assert not owned
    assert destination.read_bytes() == b"old"
    assert _mode(destination) == 0o644
    recovery = Path(failure.recovery_path)
    assert recovery.parent.parent == tmp_path
    assert _mode(recovery.parent) == 0o700
    assert _mode(recovery) == 0o600
    assert list(private_fallback_directory.iterdir()) == []
    if phase == "write":
        assert len(writes) == 1
        assert recovery.read_bytes() == yapyon.dumps(value).encode("utf-8")[:2]
        assert "not confirmed complete" in _notes(failure)
    else:
        _recovery(failure, value)
    assert "Replacement was not attempted" in _notes(failure)


def test_replace_then_raise_reports_observed_destination_and_retains_complete_fallback(
        tmp_path, monkeypatch, private_fallback_directory):
    destination = tmp_path / "existing.yap"
    destination.write_bytes(b"old")
    destination.chmod(0o644)
    original = _safe.os.replace
    failure = OSError(errno.EIO, "replace completed but acknowledgement failed")

    def replaced(*args, **kwargs):
        original(*args, **kwargs)
        raise failure

    monkeypatch.setattr(_safe.os, "replace", replaced)
    with pytest.raises(OSError) as caught:
        yapyon.dump_safe({"new": True}, destination)
    assert caught.value is failure
    assert destination.read_bytes() == b"new: True\n"
    assert _mode(destination) == 0o644
    assert "Replacement may have completed" in _notes(failure)
    assert "destination currently refers to the staged inode" in _notes(failure)
    assert "No replacement was performed" not in _notes(failure)
    assert _recovery(failure, {"new": True}).parent.parent == private_fallback_directory
    assert list(tmp_path.iterdir()) == [destination]


def test_partial_local_write_prefers_complete_fallback_when_retry_succeeds(
        tmp_path, monkeypatch, private_fallback_directory):
    destination = tmp_path / "existing.yap"
    destination.write_bytes(b"old")
    original = _safe.os.write
    failure = OSError(errno.ENOSPC, "local staging write failed")
    calls = []

    def writing(fd, data):
        calls.append(fd)
        if len(calls) == 1:
            return original(fd, data[:2])
        if len(calls) == 2:
            raise failure
        return original(fd, data)

    monkeypatch.setattr(_safe.os, "write", writing)
    with pytest.raises(OSError) as caught:
        yapyon.dump_safe({"complete": True}, destination)
    assert caught.value is failure
    assert destination.read_bytes() == b"old"
    assert _recovery(failure, {"complete": True}).parent.parent == private_fallback_directory
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.parametrize("exception_type", [PermissionError, KeyboardInterrupt])
def test_failure_before_record_creation_cleans_owned_empty_staging_directories(
        tmp_path, monkeypatch, private_fallback_directory, exception_type):
    destination = tmp_path / "existing.yap"
    destination.write_bytes(b"old")
    failure = exception_type("directory protection failed")
    original = _safe._private
    calls = []

    def private(fd, mode=0o600):
        if mode == 0o700:
            calls.append(fd)
            if len(calls) == 1:
                raise failure
            raise PermissionError("fallback protection failed")
        return original(fd, mode)

    monkeypatch.setattr(_safe, "_private", private)
    with pytest.raises(exception_type) as caught:
        yapyon.dump_safe(42, destination)
    assert caught.value is failure
    assert failure.recovery_path is None
    assert destination.read_bytes() == b"old"
    assert list(tmp_path.iterdir()) == [destination]
    assert list(private_fallback_directory.iterdir()) == []


def test_uncreated_primary_record_is_cleaned_when_only_partial_fallback_survives(
        tmp_path, monkeypatch, private_fallback_directory):
    destination = tmp_path / "existing.yap"
    destination.write_bytes(b"old")
    failure = PermissionError("primary protection failed")
    original = _safe._private
    first = []

    def private(fd, mode=0o600):
        if mode == 0o700 and not first:
            first.append(True)
            raise failure
        return original(fd, mode)

    def write(*args):
        raise OSError(errno.ENOSPC, "fallback write failed")

    monkeypatch.setattr(_safe, "_private", private)
    monkeypatch.setattr(_safe.os, "write", write)
    with pytest.raises(PermissionError) as caught:
        yapyon.dump_safe(42, destination)
    assert caught.value is failure
    assert destination.read_bytes() == b"old"
    assert list(tmp_path.iterdir()) == [destination]
    path = Path(failure.recovery_path)
    assert path.parent.parent == private_fallback_directory
    assert path.read_bytes() == b""
    assert "not confirmed complete" in _notes(failure)


def test_empty_directory_cleanup_failure_is_reported_without_masking_original(
        tmp_path, monkeypatch):
    destination = tmp_path / "existing.yap"
    destination.write_bytes(b"old")
    failure = PermissionError("directory protection failed")
    original = _safe._private

    def private(fd, mode=0o600):
        if mode == 0o700:
            raise failure
        return original(fd, mode)

    def remove(*args, **kwargs):
        raise OSError(errno.EACCES, "directory cleanup denied")

    monkeypatch.setattr(_safe, "_private", private)
    monkeypatch.setattr(_safe.os, "rmdir", remove)
    with pytest.raises(PermissionError) as caught:
        yapyon.dump_safe(42, destination)
    assert caught.value is failure
    assert failure.recovery_path is None
    assert destination.read_bytes() == b"old"
    remaining = [path for path in tmp_path.iterdir() if path != destination]
    assert len(remaining) == 1
    assert str(remaining[0]) in _notes(failure)
    assert "cleanup failed" in _notes(failure)


def test_unverified_platform_is_refused_without_claiming_private_recovery(tmp_path, monkeypatch):
    destination = tmp_path / "new.yap"
    with monkeypatch.context() as patch:
        patch.setattr(_safe.sys, "platform", "unverified")
        with pytest.raises(OSError) as caught:
            _safe.write_file("1\n", destination)
    assert caught.value.errno == errno.ENOTSUP
    assert caught.value.recovery_path is None
    assert not destination.exists()
