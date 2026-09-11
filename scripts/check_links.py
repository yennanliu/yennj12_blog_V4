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

Usage:  python3 scripts/check_links.py [--content-only] [--strict]

  --content-only   skip the built-output half (no `hugo` run needed)
  --strict         also fail on dead internal targets, not just warn
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

# A baseURL with no sub-path ("https://example.org/") leaves BASE_PATH as "/",
# which would make every root-absolute URL in the build look wrong. There is
# nothing to check in that case, so the sub-path rules switch themselves off.
HAS_SUBPATH = BASE_PATH != "/"

MD_LINK = re.compile(r"\]\(([^)\s]+)")
ATTR = re.compile(r"""(?:href|src)=(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.I)
FENCE = re.compile(r"^\s*(```+|~~~+)")

# Self-referential metadata: these are built from front matter through absURL,
# which silently drops the sub-path when the value starts with "/". They are
# not href/src, so ATTR never sees them.
META = re.compile(
    r"""<meta[^>]*?(?:property|name)=["']?"""
    r"""(og:image(?::secure_url)?|twitter:image|og:url)["']?[^>]*?"""
    r"""content=["']([^"']*)["']""",
    re.I,
)
CANONICAL = re.compile(
    r"""<link[^>]*?rel=["']?canonical["']?[^>]*?href=["']([^"']*)["']""", re.I
)


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
            if not HAS_SUBPATH:
                target = url.split("#")[0].split("?")[0]
                if target and not _exists(target):
                    dead[target] += 1
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

        if not HAS_SUBPATH:
            continue

        metadata = [(m.group(1), m.group(2)) for m in META.finditer(text)]
        metadata += [("canonical", m.group(1)) for m in CANONICAL.finditer(text)]
        for label, url in metadata:
            split = urlsplit(url)
            # Only our own host is ours to judge: the same domain also serves
            # sibling GitHub Pages projects (InvestSkill, finance_data, ...)
            # under their own sub-paths, and pointing a card at one of those is
            # a legitimate choice.
            if split.netloc != HOST:
                continue
            if split.path == BASE_PATH or split.path.startswith(BASE_PATH + "/"):
                continue
            # What separates the absURL trap from a deliberate sibling link is
            # whether this very path exists inside *our* build. If it does, the
            # sub-path was dropped off one of our own files.
            if not _exists(split.path):
                continue
            errors.append(
                f"{path.relative_to(ROOT)}: {label} is {url!r}, which is missing "
                f"the {BASE_PATH} prefix — absURL drops the sub-path when its "
                f"argument starts with a slash, so trim it first"
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
    strict = "--strict" in sys.argv

    errors = check_content()
    dead: Counter = Counter()
    if not content_only:
        public_errors, dead = check_public()
        errors += public_errors

    if dead:
        total = sum(dead.values())
        label = "error" if strict else "warning"
        print(
            f"{label}: {len(dead)} internal target(s) do not exist "
            f"({total} link(s)):"
        )
        for target, count in dead.most_common():
            print(f"  {label}:  {count:4d}x  {target}")
        if strict:
            errors += [
                f"dead internal target: {target} ({count} link(s))"
                for target, count in dead.most_common()
            ]

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
