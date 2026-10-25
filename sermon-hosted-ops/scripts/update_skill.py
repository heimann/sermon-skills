#!/usr/bin/env python3
"""Check this Sermon skill copy against the canonical copy and replace it when safe.

Uses only Sermon's public skill and manifest endpoints on the trusted origin.
Sends no credentials, refuses redirects, and never executes downloaded content.
Writes only inside the skill directory, reached without symlinks (POSIX only).
"""

import argparse
import hashlib
import json
import os
import secrets
import stat
import sys
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

DEFAULT_ORIGIN = "https://sermon.fyi"
SKILL_PATH = "/docs/agents/skill.md"
MANIFEST_PATH = "/docs/agents/manifest.json"
SKILL_FILE = "SKILL.md"
STATE_FILE = "managed.json"
ASIDE_PREFIX = ".sermon-skill-aside-"
MAX_BYTES = 1024 * 1024
TIMEOUT = 10

EXIT_STALE = 1
EXIT_USAGE = 2
EXIT_CONFLICT = 3
EXIT_UNVERIFIED = 4
EXIT_INTEGRITY = 5

UNVERIFIED_ADVICE = (
    "Continue with the cached SKILL.md, and tell the user its freshness is unverified. "
    "Do not conclude that Sermon lacks a capability from the cached copy alone; "
    "check the live Sermon MCP tool list first."
)


class Failure(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class RefuseRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Failure(EXIT_UNVERIFIED, f"refused HTTP {code} redirect from {req.full_url}")


OPENER = build_opener(RefuseRedirects())


def trusted_origin(value):
    parsed = urlsplit(value)
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (parsed.scheme == "http" and local):
        raise Failure(EXIT_USAGE, "origin must use HTTPS (HTTP is allowed only for localhost)")
    try:
        port = parsed.port
    except ValueError:
        port = -1
    if (not parsed.hostname or parsed.hostname.endswith(".") or "@" in parsed.netloc or port == -1
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise Failure(EXIT_USAGE, "origin must be scheme://host[:port] without credentials, path, query, or fragment")
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    default = {"https": 443, "http": 80}[parsed.scheme]
    return f"{parsed.scheme}://{host}" + (f":{port}" if port not in (None, default) else "")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def etag_for(digest):
    return f'"sha256-{digest}"'


def fetch(url, headers):
    request = Request(url, headers={"Accept-Encoding": "identity", **headers})
    try:
        with OPENER.open(request, timeout=TIMEOUT) as response:
            body = response.read(MAX_BYTES + 1)
    except HTTPError as error:
        if error.code == 304:
            return 304, error.headers, b""
        raise Failure(EXIT_UNVERIFIED, f"{url} returned HTTP {error.code}") from None
    except (URLError, OSError, HTTPException) as error:
        raise Failure(EXIT_UNVERIFIED, f"could not reach {url} ({error})") from None
    if len(body) > MAX_BYTES:
        raise Failure(EXIT_INTEGRITY, f"{url} exceeded {MAX_BYTES} bytes")
    return response.status, response.headers, body


def open_dir(path):
    """Open the skill directory one component at a time, refusing symlinks.

    Every later read and write goes through the returned descriptor, so moving
    or relinking the path during the network fetch cannot redirect a write.
    """
    absolute = os.path.abspath(path)
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in filter(None, absolute.split(os.sep)):
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
    except OSError:
        os.close(fd)
        raise Failure(EXIT_USAGE, f"{absolute} is not a directory reachable without symlinks; pass its resolved path") from None
    return fd


def read_file(dfd, name):
    """Bytes of a regular, non-symlink file in the directory; None when absent."""
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dfd)
    except FileNotFoundError:
        return None
    except OSError:
        raise Failure(EXIT_USAGE, f"{name} is not a regular file; refusing to use it") from None
    with os.fdopen(fd, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise Failure(EXIT_USAGE, f"{name} is not a regular file; refusing to use it")
        data = handle.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise Failure(EXIT_USAGE, f"{name} exceeds {MAX_BYTES} bytes")
    return data


def ownership(dfd, origin, local_digest):
    """(managed, unmodified) for the local copy, from managed.json."""
    try:
        raw = read_file(dfd, STATE_FILE)
        state = json.loads(raw) if raw is not None else None
    except (Failure, ValueError):
        state = None
    managed = (isinstance(state, dict) and state.get("origin") == origin
               and isinstance(state.get("sha256"), str) and len(state["sha256"]) == 64)
    return managed, managed and state["sha256"] == local_digest


def write_temp(dfd, data):
    name = f".sermon-skill-{secrets.token_hex(8)}"
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=dfd)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fchmod(handle.fileno(), 0o644)
            os.fsync(handle.fileno())
    except BaseException:
        os.unlink(name, dir_fd=dfd)
        raise
    return name


def link_new(dfd, source, target):
    """Give `source` the name `target` only if `target` does not exist; links never overwrite."""
    try:
        os.link(source, target, src_dir_fd=dfd, dst_dir_fd=dfd, follow_symlinks=False)
        return True
    except FileExistsError:
        return False


def write_state(dfd, origin, digest):
    state = json.dumps({"origin": origin, "sha256": digest}, sort_keys=True, indent=2) + "\n"
    # os.replace swaps the directory entry itself, so it never writes through a link.
    os.replace(write_temp(dfd, state.encode()), STATE_FILE, src_dir_fd=dfd, dst_dir_fd=dfd)


def recover_interrupted_swap(dfd):
    """Restore SKILL.md from a copy set aside by a run that was killed mid-swap.

    Only this script creates aside files. A lone aside is restored whatever its
    hash, which covers --adopt on an unmanaged copy; among several, only the one
    managed.json records is restored. Links never overwrite, so nothing is lost.
    """
    if read_file(dfd, SKILL_FILE) is not None:
        return
    asides = sorted(name for name in os.listdir(dfd) if name.startswith(ASIDE_PREFIX))
    if len(asides) > 1:
        try:
            recorded = json.loads(read_file(dfd, STATE_FILE) or b"null")
        except (Failure, ValueError):
            recorded = None
        expected = recorded.get("sha256") if isinstance(recorded, dict) else None
        asides = [name for name in asides if sha256(read_file(dfd, name) or b"") == expected][:1]
    for name in asides:
        if link_new(dfd, name, SKILL_FILE):
            os.unlink(name, dir_fd=dfd)
            print("sermon-skill: restored SKILL.md from an interrupted update")


class Changed(Exception):
    """SKILL.md changed between the first read and the replacement."""


def replace_skill(dfd, expected, canonical):
    """Install `canonical` as SKILL.md only if SKILL.md still holds `expected`.

    The current SKILL.md inode is renamed aside and never deleted: an edit that
    lands before the swap is detected and restored, and a write through a
    handle that is still open afterwards survives in the backup. Links refuse
    to overwrite, so a SKILL.md created mid-swap is never clobbered.
    Returns the backup name.
    """
    aside = f"{ASIDE_PREFIX}{secrets.token_hex(8)}"
    try:
        os.rename(SKILL_FILE, aside, src_dir_fd=dfd, dst_dir_fd=dfd)
    except FileNotFoundError:
        raise Changed("SKILL.md disappeared while updating; nothing was replaced") from None
    try:
        try:
            moved = read_file(dfd, aside)
        except Failure:
            moved = None
        if moved != expected:
            restored = link_new(dfd, aside, SKILL_FILE)
            if restored:
                os.unlink(aside, dir_fd=dfd)
            raise Changed(f"SKILL.md changed while updating; kept the changed copy at {SKILL_FILE if restored else aside} "
                          "and replaced nothing")
        temp = write_temp(dfd, canonical)
        installed = link_new(dfd, temp, SKILL_FILE)
        os.unlink(temp, dir_fd=dfd)
    except Changed:
        raise
    except BaseException:
        # Interrupted before the canonical copy was linked in: put the original back.
        if link_new(dfd, aside, SKILL_FILE):
            os.unlink(aside, dir_fd=dfd)
        raise
    backup = f"{SKILL_FILE}.previous-{sha256(expected)[:12]}"
    if not link_new(dfd, aside, backup):
        backup = f"{backup}.{secrets.token_hex(4)}"
        if not link_new(dfd, aside, backup):
            backup = aside
    if backup != aside:
        os.unlink(aside, dir_fd=dfd)
    if not installed:
        raise Changed(f"a new SKILL.md appeared while updating; kept it, and the previous copy at {backup}")
    return backup


def verified_canonical(origin, headers, body):
    """Reject a downloaded skill unless its ETag and the manifest both name its exact hash."""
    digest = sha256(body)
    if headers.get("ETag") != etag_for(digest):
        raise Failure(EXIT_INTEGRITY, "skill bytes do not match the served ETag")
    if not headers.get("Content-Type", "").startswith("text/markdown"):
        raise Failure(EXIT_INTEGRITY, "skill endpoint did not return Markdown")
    try:
        body.decode("utf-8")
    except UnicodeDecodeError:
        raise Failure(EXIT_INTEGRITY, "skill is not UTF-8") from None
    status, _headers, raw = fetch(origin + MANIFEST_PATH, {"Accept": "application/json"})
    try:
        manifest = json.loads(raw) if status == 200 else None
        skill = manifest["skill"]
        matches = (manifest["schema_version"] == 1 and skill["url"] == origin + SKILL_PATH
                   and skill["sha256"] == digest)
    except (ValueError, TypeError, KeyError):
        matches = False
    if not matches:
        raise Failure(EXIT_INTEGRITY, "manifest does not vouch for the downloaded skill")
    return digest


def conflict(reason, body):
    print(
        f"sermon-skill: conflict: {reason}.\n"
        "Tell the user, and follow the canonical instructions below for this session instead of the local copy.\n"
        "To replace the local copy with the managed canonical skill, rerun with --adopt (it keeps a backup).\n"
    )
    sys.stdout.write(body.decode("utf-8"))
    return EXIT_CONFLICT


def run(args):
    origin = trusted_origin(args.origin)
    dfd = open_dir(args.skill_dir)
    try:
        return update(args, origin, dfd)
    finally:
        os.close(dfd)


def update(args, origin, dfd):
    if not args.check:
        recover_interrupted_swap(dfd)
    local = read_file(dfd, SKILL_FILE)
    if local is None:
        raise Failure(EXIT_USAGE, f"{SKILL_FILE} does not exist in {args.skill_dir}")
    local_digest = sha256(local)
    managed, unmodified = ownership(dfd, origin, local_digest)

    status, headers, body = fetch(origin + SKILL_PATH, {
        "Accept": "text/markdown",
        "If-None-Match": etag_for(local_digest),
    })
    if status not in (200, 304):
        raise Failure(EXIT_UNVERIFIED, f"{origin}{SKILL_PATH} returned HTTP {status}")
    if status == 200:
        canonical_digest = verified_canonical(origin, headers, body)
    if status == 304 or canonical_digest == local_digest:
        # Also repairs a managed copy whose state write was interrupted after its replacement.
        if (managed or args.adopt) and not unmodified and not args.check:
            write_state(dfd, origin, local_digest)
        print(f"sermon-skill: current {local_digest[:12]} from {origin}")
        return 0

    if args.check:
        print(f"sermon-skill: stale {local_digest[:12]}; canonical is {canonical_digest[:12]} at {origin}")
        return EXIT_STALE

    if not unmodified and not args.adopt:
        reason = "customized since it was installed" if managed else f"not managed by this updater for {origin}"
        return conflict(f"the local SKILL.md is {reason}, so it was not replaced", body)

    # Ownership and content are rechecked at the swap itself, not trusted from before the fetch.
    if ownership(dfd, origin, local_digest) != (managed, unmodified):
        return conflict("managed.json changed while updating, so SKILL.md was not replaced", body)
    try:
        backup = replace_skill(dfd, local, body)
    except Changed as changed:
        return conflict(str(changed), body)
    write_state(dfd, origin, canonical_digest)
    print(f"sermon-skill: updated {local_digest[:12]} -> {canonical_digest[:12]} from {origin}; "
          f"kept the previous copy as {backup}; reread SKILL.md before continuing")
    return 0


def parser():
    default_dir = Path(__file__).resolve().parent.parent
    p = argparse.ArgumentParser(description="Check the Sermon skill copy against the canonical skill and replace it when safe.")
    p.add_argument("--origin", default=os.environ.get("SERMON_URL") or DEFAULT_ORIGIN,
                   help="trusted Sermon origin (default: $SERMON_URL or https://sermon.fyi)")
    p.add_argument("--skill-dir", default=str(default_dir), help="directory holding SKILL.md (default: %(default)s)")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="report current or stale without writing anything")
    mode.add_argument("--adopt", action="store_true",
                      help="one-time migration: back up an unmanaged or customized copy, then install the canonical skill")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        return run(args)
    except OSError as error:
        print(f"sermon-skill: freshness-unverified: could not finish updating {args.skill_dir} ({error.strerror}); "
              f"reread SKILL.md, which may or may not have been replaced. {UNVERIFIED_ADVICE}")
        return EXIT_UNVERIFIED
    except Failure as failure:
        if failure.code == EXIT_USAGE:
            print(f"sermon-skill: error: {failure}", file=sys.stderr)
        elif failure.code == EXIT_INTEGRITY:
            print(f"sermon-skill: integrity-mismatch: {failure}; nothing was replaced. {UNVERIFIED_ADVICE}")
        else:
            print(f"sermon-skill: freshness-unverified: {failure}. {UNVERIFIED_ADVICE}")
        return failure.code


if __name__ == "__main__":
    raise SystemExit(main())
