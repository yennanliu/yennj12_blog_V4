#!/usr/bin/env python3
"""Guard against internal links that drop the baseURL sub-path.

The site is served from a sub-path (https://yennj12.js.org/yennj12_blog_V4/), so
any href/src that starts with a bare "/" points at the domain root and 404s.
This is the class of bug that made links like

    https://yennj12.js.org/posts/aio-geo-part2-how-engines-work-zh/

dead while the real page lived at

    https://yennj12.js.org/yennj12_blog_V4/posts/aio-geo-part2-how-engines-work-zh/

Two checks run, and each is an error:

  1. content/  — no hard-coded baseURL (the sub-path or the full domain) in a
     Markdown link. Write "/posts/slug/" and let the link render hook
     (themes/uber-style/layouts/_default/_markup/render-link.html) resolve it.
  2. public/   — every root-absolute href/src in the built site must sit under
     the baseURL path. This catches templates that forget relURL, and the
     relURL leading-slash trap: `relURL "/tags/x/"` returns "/tags/x/"
     unchanged, only `relURL "tags/x/"` prepends the sub-path.

Dead internal targets (links to pages that were never written) are reported as
warnings; they are a content problem, not a URL-shape problem, and do not fail
the build.

Usage:  python3 scripts/check_links.py [--content-only]
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
PUBLIC = ROOT / "public"

def _base_url() -> str:
    """Read baseURL out of hugo.toml so this script cannot drift from the site."""
    for line in (ROOT / "hugo.toml").read_text(encoding="utf-8").split("\n"):
        key, sep, value = line.partition("=")
        if sep and key.strip() == "baseURL":
            return value.strip().strip("'\"")
    raise SystemExit("error: no baseURL in hugo.toml")


_BASE = urlsplit(_base_url())
BASE_PATH = "/" + _BASE.path.strip("/")          # "/yennj12_blog_V4"
HOST = _BASE.netloc                              # "yennj12.js.org"

MD_LINK = re.compile(r"\]\(([^)\s]+)")
ATTR = re.compile(r"""(?:href|src)=(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.I)
FENCE = re.compile(r"^\s*(```+|~~~+)")


def markdown_links(text: str):
    """Yield (line_no, url) for Markdown links outside fenced code blocks.

    Fence matching follows CommonMark: a block opened with N markers closes
    only on a run of the *same* character that is at least N long. Truncating
    the delimiter would let an inner ``` close an outer ````, after which a
    URL inside that code sample would be reported as a real link.
    """
    fence = None
    for n, line in enumerate(text.split("\n"), 1):
        m = FENCE.match(line)
        if m:
            token = m.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            continue
        if fence:
            continue
        for link in MD_LINK.finditer(line):
            yield n, link.group(1)


def check_content() -> list[str]:
    errors = []
    for path in sorted(CONTENT.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        for line_no, url in markdown_links(text):
            hardcoded = url.startswith(BASE_PATH + "/") or url == BASE_PATH or any(
                url.startswith(scheme + HOST + BASE_PATH)
                for scheme in ("http://", "https://")
            )
            if hardcoded:
                errors.append(
                    f"{path.relative_to(ROOT)}:{line_no}: hard-coded baseURL in "
                    f"link {url!r} — drop the {BASE_PATH} prefix and let the "
                    f"render hook resolve it"
                )
    return errors


def check_public() -> tuple[list[str], Counter]:
    errors: list[str] = []
    dead: Counter = Counter()
    if not PUBLIC.is_dir():
        return [f"{PUBLIC.relative_to(ROOT)}/ not found — run `hugo --minify` first"], dead

    for path in PUBLIC.rglob("*.html"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in ATTR.finditer(text):
            url = match.group(1) or match.group(2) or match.group(3) or ""
            if not url.startswith("/") or url.startswith("//"):
                continue
            if url == BASE_PATH or url.startswith(BASE_PATH + "/"):
                target = url[len(BASE_PATH):].split("#")[0].split("?")[0]
                if target and not _exists(target):
                    dead[target] += 1
                continue
            errors.append(
                f"{path.relative_to(ROOT)}: {url!r} is missing the {BASE_PATH} "
                f"prefix — use relURL with a path that has no leading slash"
            )
    return errors, dead


def _exists(target: str) -> bool:
    rel = unquote(target).lstrip("/")
    if not rel:
        return True
    candidate = PUBLIC / rel
    return candidate.is_file() or (candidate / "index.html").is_file()


def main() -> int:
    content_only = "--content-only" in sys.argv

    errors = check_content()
    dead: Counter = Counter()
    if not content_only:
        public_errors, dead = check_public()
        errors += public_errors

    if dead:
        total = sum(dead.values())
        print(
            f"warning: {len(dead)} internal target(s) do not exist "
            f"({total} link(s)); showing 15:"
        )
        for target, count in dead.most_common(15):
            print(f"  warning:  {count:4d}x  {target}")

    if errors:
        print(f"\nerror: {len(errors)} internal link(s) missing the site sub-path:")
        for message in errors[:40]:
            print(f"  {message}")
        if len(errors) > 40:
            print(f"  ... and {len(errors) - 40} more")
        return 1

    print("ok: every internal link carries the site sub-path")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
