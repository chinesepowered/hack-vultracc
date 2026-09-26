"""Read and write sandbox directories on the host without trusting their contents.

Everything a sandbox writes is hostile: files may be symlinks pointing at host
paths, FIFOs, devices, or huge. These helpers never follow symlinks, only
touch regular files, stay inside the directory, and cap sizes and counts.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
from pathlib import Path

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_FILES = 200
MAX_TOTAL_BYTES = 80 * 1024 * 1024


class UnsafePath(ValueError):
    pass


def check_name(name: str) -> str:
    """Only plain file names (no directories, no dot-files, no traversal)."""
    if not NAME_RE.match(name or "") or name in (".", ".."):
        raise UnsafePath(f"unsafe file name {name!r}")
    return name


def write_file(directory: Path, name: str, data: bytes, mode: int = 0o644) -> None:
    """Create or replace directory/name without following symlinks."""
    check_name(name)
    dfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        try:
            st = os.lstat(name, dir_fd=dfd)
            if not stat.S_ISREG(st.st_mode):
                raise UnsafePath(f"{name} exists and is not a regular file")
            os.unlink(name, dir_fd=dfd)
        except FileNotFoundError:
            pass
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=dfd)
        try:
            os.write(fd, data)
        finally:
            os.close(fd)
    finally:
        os.close(dfd)


def read_file(directory: Path, name: str, max_bytes: int = MAX_FILE_BYTES) -> bytes:
    """Read a regular file directly inside directory, refusing symlinks and specials."""
    check_name(name)
    dfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dfd)
    except OSError as exc:
        raise UnsafePath(f"cannot open {name}: {exc.strerror}") from None
    finally:
        os.close(dfd)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise UnsafePath(f"{name} is not a regular file")
        if st.st_size > max_bytes:
            raise UnsafePath(f"{name} is {st.st_size} bytes, over the {max_bytes} byte cap")
        chunks, total = [], 0
        while True:
            b = os.read(fd, 1 << 16)
            if not b:
                break
            total += len(b)
            if total > max_bytes:
                raise UnsafePath(f"{name} grew past the size cap while reading")
            chunks.append(b)
        return b"".join(chunks)
    finally:
        os.close(fd)


def list_outputs(directory: Path) -> tuple[list[dict], list[dict]]:
    """List regular files directly inside directory with size and sha256.

    Returns (files, rejected). Subdirectories, symlinks and special files are
    rejected, not followed. Caps the count and total size.
    """
    files, rejected, total = [], [], 0
    try:
        entries = sorted(os.scandir(directory), key=lambda e: e.name)
    except FileNotFoundError:
        return [], []
    for entry in entries:
        if len(files) >= MAX_FILES:
            rejected.append({"path": entry.name, "reason": "too many files"})
            continue
        try:
            st = entry.stat(follow_symlinks=False)
        except OSError as exc:
            rejected.append({"path": entry.name, "reason": exc.strerror or "stat failed"})
            continue
        if stat.S_ISLNK(st.st_mode):
            rejected.append({"path": entry.name, "reason": "symlink (not followed)"})
            continue
        if not stat.S_ISREG(st.st_mode):
            rejected.append({"path": entry.name, "reason": "not a regular file"})
            continue
        if not NAME_RE.match(entry.name):
            rejected.append({"path": entry.name, "reason": "unsafe name"})
            continue
        if st.st_size > MAX_FILE_BYTES or total + st.st_size > MAX_TOTAL_BYTES:
            rejected.append({"path": entry.name, "reason": "over size cap"})
            continue
        try:
            data = read_file(directory, entry.name)
        except UnsafePath as exc:
            rejected.append({"path": entry.name, "reason": str(exc)})
            continue
        total += len(data)
        files.append({"path": entry.name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    return files, rejected
