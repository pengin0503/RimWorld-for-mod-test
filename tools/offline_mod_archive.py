"""Bounded, read-only MOD ZIP staging for offline static preflight.

Only XML needed by the static scanner is decompressed. Other file names are
represented by empty placeholders solely to preserve version-folder selection.
No game/Workshop content or archive contents are written to the repository.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import re
import stat
from tempfile import TemporaryDirectory
from zipfile import ZipFile, BadZipFile

MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024
MAX_MEMBERS = 20_000
MAX_XML_BYTES = 4 * 1024 * 1024
MAX_SELECTED_XML_BYTES = 32 * 1024 * 1024
_DIR_MARKER = ".rwmt-offline-directory"


class OfflineArchiveError(ValueError):
    """Archive cannot safely be mapped to one static MOD tree."""


def _check_archive_member(info) -> tuple[str, ...]:
    name = info.filename
    # Reject paths that change meaning across Linux/Windows or have aliases.
    if (not name or "\0" in name or "\\" in name or name.startswith("/")
            or any(ord(char) < 32 for char in name)):
        raise OfflineArchiveError("unsafe archive path")
    cleaned = name[:-1] if info.is_dir() else name
    parts = tuple(cleaned.split("/"))
    if (not cleaned or any(part in ("", ".", "..") or ":" in part
                           or part.endswith((" ", ".")) or part.casefold() == _DIR_MARKER
                           for part in parts)):
        raise OfflineArchiveError("unsafe archive path")
    if any(re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", p) for p in parts):
        raise OfflineArchiveError("Windows-incompatible archive path")
    mode = (info.external_attr >> 16) & 0xFFFF
    kind = stat.S_IFMT(mode)
    if kind not in (0, stat.S_IFREG, stat.S_IFDIR):
        raise OfflineArchiveError("archive contains a link or unsupported entry")
    if (info.flag_bits & 1) or info.file_size < 0:
        raise OfflineArchiveError("encrypted or invalid archive entry")
    return parts


def _relevant_xml(relative: str) -> bool:
    path = relative.casefold()
    if path in ("about/about.xml", "loadfolders.xml"):
        return True
    if not path.endswith(".xml"):
        return False
    # A scanner only parses Defs and Patches. No need to decompress textures,
    # languages, debug files, assemblies, shader or arbitrary extra XML.
    parts = path.split("/")
    return any(part in ("defs", "patches") for part in parts[:-1])


@contextmanager
def stage_mod_archive(archive: Path):
    """Yield a temporary file tree to the existing 1.7.4985 offline scanner.

    An exact, unique About/About.xml identifies the MOD root, optionally inside
    a wrapper directory. Refuse uncertain layouts instead of guessing which
    MOD to scan. Every entry's path is validated before any files are staged.
    """
    archive = Path(archive).absolute()
    if (not archive.is_file() or archive.is_symlink()
            or any(parent.is_symlink() for parent in archive.parents)
            or archive.stat().st_size > MAX_ARCHIVE_BYTES):
        raise OfflineArchiveError("missing, linked or oversized archive")
    try:
        with ZipFile(archive) as zip_file:
            infos = zip_file.infolist()
            if not infos or len(infos) > MAX_MEMBERS:
                raise OfflineArchiveError("invalid archive entry count")
            parsed = []
            spellings = {}
            for info in infos:
                parts = _check_archive_member(info)
                # Reject case-insensitive ambiguities at *every directory level*
                # before staging on a case-sensitive or insensitive filesystem.
                for index in range(1, len(parts) + 1):
                    key = tuple(p.casefold() for p in parts[:index])
                    display = parts[:index]
                    if key in spellings and spellings[key] != display:
                        raise OfflineArchiveError("ambiguous case-folded archive path")
                    spellings[key] = display
                parsed.append((info, parts))
            roots = [parts[:-2] for info, parts in parsed
                     if not info.is_dir() and len(parts) >= 2
                     and parts[-2:] == ("About", "About.xml")]
            if len(roots) != 1:
                raise OfflineArchiveError("archive must contain exactly one MOD root")
            wrapper = roots[0]
            entries = []
            used = set()
            for info, parts in parsed:
                if parts[:len(wrapper)] != wrapper:
                    raise OfflineArchiveError("archive contains unrelated root entries")
                relative = parts[len(wrapper):]
                if not relative:
                    if not info.is_dir():
                        raise OfflineArchiveError("archive wrapper is not a folder")
                    continue
                key = tuple(p.casefold() for p in relative)
                if key in used:
                    raise OfflineArchiveError("duplicate archive member")
                used.add(key)
                entries.append((info, relative))
            with TemporaryDirectory(prefix="rwmt-offline-") as work:
                root = Path(work)
                xml_bytes = 0
                for info, relative in entries:
                    destination = root.joinpath(*relative)
                    if info.is_dir():
                        destination.mkdir(parents=True, exist_ok=True)
                        # Explicit empty version directories influence loader
                        # fallback even when they contain no real file entries.
                        (destination / _DIR_MARKER).touch(exist_ok=True)
                        continue
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    if not _relevant_xml("/".join(relative)):
                        destination.touch(exist_ok=False)
                        continue
                    xml_bytes += info.file_size
                    if info.file_size > MAX_XML_BYTES or xml_bytes > MAX_SELECTED_XML_BYTES:
                        raise OfflineArchiveError("archive XML exceeds offline read budget")
                    with zip_file.open(info, "r") as input_stream:
                        data = input_stream.read(MAX_XML_BYTES + 1)
                    if len(data) != info.file_size:
                        raise OfflineArchiveError("invalid bounded XML content")
                    destination.write_bytes(data)
                yield root
    except (BadZipFile, EOFError, RuntimeError) as exc:
        raise OfflineArchiveError("cannot safely read archive") from exc
