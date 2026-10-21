"""The environment a document may read — SPEC §5.1.3 and §5.1.4.

A hole reads **the environment of the process loading the document** and no
other: `{$NAME}` strictly, `{__ENV__("NAME", fallback)}` with a fallback.
Both go through `Environment.get`, the one lookup.

**Not every variable is exposed.** A load sees the standard variables of its
environment system unless the caller says otherwise, because a process's
environment commonly holds credentials and a document can come from somewhere
less trusted than the process. A variable that is not exposed is
indistinguishable from one that is unset.

The standard sets below are what SPEC §5.1.4's criteria give over its pinned
sources — the spec states the criteria, not a list, so these are this
implementation's reading of them, kept in step by `tests/test_environment.py`.
"""

from __future__ import annotations

import os

#: The Open Group Base Specifications, Issue 8, ch. 8 (all of it passes the
#: criteria), and the XDG Base Directory Specification 0.8.
POSIX_STANDARD_ENV = frozenset({
    # 8.2, internationalization
    "LANG", "LANGUAGE", "LC_ALL", "LC_COLLATE", "LC_CTYPE", "LC_MESSAGES",
    "LC_MONETARY", "LC_NUMERIC", "LC_TIME", "NLSPATH", "TEXTDOMAIN",
    "TEXTDOMAINDIR",
    # 8.3, other
    "COLUMNS", "DATEMSK", "HOME", "LINES", "LOGNAME", "MSGVERB", "PATH",
    "PWD", "SHELL", "TMPDIR", "TERM", "TZ",
    # XDG Base Directory 0.8
    "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME",
    "XDG_RUNTIME_DIR", "XDG_DATA_DIRS", "XDG_CONFIG_DIRS",
})

#: Microsoft's DoEnvironmentSubst remarks ("standard"), WOW64 Implementation
#: Details, and GetTempPath, at the commits SPEC §5.1.4 pins.
WINDOWS_STANDARD_ENV = frozenset({
    # DoEnvironmentSubst: interactive applications and services
    "ALLUSERSPROFILE", "APPDATA", "COMPUTERNAME", "LOCALAPPDATA",
    "NUMBER_OF_PROCESSORS", "OS", "PROCESSOR_ARCHITECTURE",
    "PROCESSOR_IDENTIFIER", "PROCESSOR_LEVEL", "PROCESSOR_REVISION",
    "ProgramData", "ProgramFiles", "PUBLIC", "SystemDrive", "SystemRoot",
    "USERPROFILE", "windir",
    # DoEnvironmentSubst: interactive applications only
    "HOMEDRIVE", "HOMEPATH", "LOGONSERVER", "USERDOMAIN", "USERNAME",
    # WOW64
    "ProgramFiles(x86)", "ProgramW6432", "CommonProgramFiles",
    "CommonProgramFiles(x86)", "CommonProgramW6432", "PROCESSOR_ARCHITEW6432",
    # GetTempPath
    "TMP", "TEMP",
})

#: SPEC §5.1.4: Windows-compatible where the host's environment is Windows',
#: POSIX-compatible everywhere else (Cygwin and MSYS2 Pythons included).
WINDOWS = os.name == "nt"

#: The standard variables of the environment system this process runs on —
#: the default for `env_allow`.
STANDARD_ENV = WINDOWS_STANDARD_ENV if WINDOWS else POSIX_STANDARD_ENV


class _EnvAll:
    """`env_allow=ENV_ALL`: expose every variable `env` holds. A sentinel
    rather than `None`, which could be read as "allow nothing"."""

    __slots__ = ()

    def __repr__(self):
        return "yapyon.ENV_ALL"


ENV_ALL = _EnvAll()

NOT_FOUND = "is not set, or not exposed by this application"
ACCESS_OFF = "environment access is off"


class EnvValueError(ValueError):
    """A value that is not valid Unicode text (SPEC §5.1.3). The resolver
    turns it into an akan at the reference."""


class Environment:
    """One load's view of the environment: a snapshot, filtered.

    Built once when the load starts, so every reference in that load sees
    the same values (§5.1.3) whatever the process does meanwhile. Names
    compare as the environment system compares them — exactly on POSIX,
    ignoring case on Windows — for deciding what is exposed and for finding
    it alike.
    """

    __slots__ = ("_values",)

    def __init__(self, env, env_allow, *, windows: bool = WINDOWS):
        fold = str.upper if windows else (lambda name: name)
        if env_allow is not ENV_ALL:
            if isinstance(env_allow, str):
                raise TypeError("env_allow takes a set of names, not one "
                                "string")
            allowed = set()
            for name in env_allow:
                if not isinstance(name, str):
                    raise TypeError(f"env_allow names must be str, not "
                                    f"{type(name).__name__}")
                allowed.add(fold(name))
        values = {}
        for name, value in env.items():
            if not isinstance(name, str) or not isinstance(value, str):
                raise TypeError(f"env must map str to str; {name!r} maps to "
                                f"a {type(value).__name__}")
            key = fold(name)
            if env_allow is ENV_ALL or key in allowed:
                values[key] = value
        self._values = (values, fold)

    def get(self, name: str) -> str | None:
        """The value, or None when not found (unset *or* not exposed)."""
        values, fold = self._values
        value = values.get(fold(name))
        if value is not None:
            try:
                value.encode("utf-8")
            except UnicodeEncodeError:
                # POSIX holds bytes; Python decodes undecodable ones to lone
                # surrogates. A str holding those is not text, and splicing it
                # would invent characters.
                raise EnvValueError(f"${name}'s value is not valid Unicode "
                                    f"text") from None
        return value


def environment(env, env_allow) -> Environment | None:
    """The loader's arguments to the resolver's view; None when access is
    off (`env=None`)."""
    if env is None:
        return None
    return Environment(env, env_allow)
