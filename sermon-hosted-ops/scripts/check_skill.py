#!/usr/bin/env python3
"""Check this Sermon skill copy against the canonical skill, read-only.

Prints `current` when the local SKILL.md matches the canonical bytes, or the
verified canonical skill for this session when it does not. Never writes a
file, sends credentials, follows redirects, or runs downloaded content.
"""

import argparse
import hashlib
import os
import sys
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

DEFAULT_ORIGIN = "https://sermon.fyi"
SKILL_PATH = "/docs/agents/skill.md"
MAX_BYTES = 1024 * 1024
TIMEOUT = 10

EXIT_USAGE = 2
EXIT_UNVERIFIED = 4

UNVERIFIED_ADVICE = (
    "Continue with the local SKILL.md, and tell the user its freshness is unverified. "
    "Do not conclude that Sermon lacks a capability from the local copy alone; "
    "check the live Sermon MCP tool list first."
)


class Failure(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class RefuseRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Failure("freshness-unverified", f"refused HTTP {code} redirect from {req.full_url}")


OPENER = build_opener(RefuseRedirects())


def trusted_origin(value):
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError:
        port = -1
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (parsed.scheme == "http" and local):
        raise ValueError("origin must use HTTPS (HTTP is allowed only for localhost)")
    if (not parsed.hostname or parsed.hostname.endswith(".") or "@" in parsed.netloc or port == -1
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise ValueError("origin must be scheme://host[:port] without credentials, path, query, or fragment")
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    default = {"https": 443, "http": 80}[parsed.scheme]
    return f"{parsed.scheme}://{host}" + (f":{port}" if port not in (None, default) else "")


def etag_for(data):
    return f'"sha256-{hashlib.sha256(data).hexdigest()}"'


def fetch(url, local_etag):
    request = Request(url, headers={"Accept": "text/markdown", "Accept-Encoding": "identity",
                                    "If-None-Match": local_etag})
    try:
        with OPENER.open(request, timeout=TIMEOUT) as response:
            return response.status, response.headers, response.read(MAX_BYTES + 1)
    except HTTPError as error:
        if error.code == 304:
            return 304, error.headers, b""
        raise Failure("freshness-unverified", f"{url} returned HTTP {error.code}") from None
    except (URLError, OSError, HTTPException) as error:
        raise Failure("freshness-unverified", f"could not reach {url} ({error})") from None


def check(origin, local):
    url = origin + SKILL_PATH
    local_etag = etag_for(local)
    status, headers, body = fetch(url, local_etag)
    if status == 304:
        return f"sermon-skill: current {local_etag[8:20]} from {origin}\n"
    if status != 200:
        raise Failure("freshness-unverified", f"{url} returned HTTP {status}")
    if len(body) > MAX_BYTES or headers.get("ETag") != etag_for(body):
        raise Failure("integrity-mismatch", "the downloaded skill does not match its ETag")
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        raise Failure("integrity-mismatch", "the downloaded skill is not UTF-8") from None
    return (
        f"sermon-skill: refreshed: the local SKILL.md is stale. Follow the canonical skill below for this "
        f"session instead of the local copy. The local file was not changed; tell the user it can be "
        f"reinstalled.\n\n{text}"
    )


def main(argv=None):
    default_skill = Path(__file__).resolve().parent.parent / "SKILL.md"
    parser = argparse.ArgumentParser(description="Check the Sermon skill copy against the canonical skill without writing files.")
    parser.add_argument("--origin", default=os.environ.get("SERMON_URL") or DEFAULT_ORIGIN,
                        help="trusted Sermon origin (default: $SERMON_URL or https://sermon.fyi)")
    parser.add_argument("--skill", default=str(default_skill), help="local SKILL.md (default: %(default)s)")
    args = parser.parse_args(argv)
    try:
        origin = trusted_origin(args.origin)
    except ValueError as error:
        print(f"sermon-skill: error: {error}", file=sys.stderr)
        return EXIT_USAGE
    try:
        local = Path(args.skill).read_bytes()
    except OSError as error:
        print(f"sermon-skill: error: could not read {args.skill} ({error.strerror})", file=sys.stderr)
        return EXIT_USAGE
    try:
        output, code = check(origin, local), 0
    except Failure as failure:
        output, code = f"sermon-skill: {failure.status}: {failure}. {UNVERIFIED_ADVICE}\n", EXIT_UNVERIFIED
    # Bytes, so a terminal that cannot encode the skill's UTF-8 still receives it intact.
    sys.stdout.buffer.write(output.encode("utf-8"))
    sys.stdout.flush()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
