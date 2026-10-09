#!/usr/bin/env python3
"""Mechanical review of blog posts: front matter, format and series house rules.

This is the deterministic half of the blog reviewer. It checks what a script
can check without judgement; the judgement half (is the explanation clear, are
the numbers right, is the argument honest) lives in the `blog-reviewer` skill
under .claude/skills/, and CI runs that one through Claude when an API key is
configured.

Two severities:

  error    Always wrong, on any post. Broken or missing front matter, a
           category outside the closed set, an author with no profile, an
           unclosed code fence, an image that is not in static/. These fail
           the run.
  warning  A house-style rule from CLAUDE.md that older posts predate — the
           fde-interview-guide "no Google" rule, section caps, line targets,
           readTime drift. Reported, but only --strict fails on them, so
           touching a legacy post does not force a rewrite of it.

The closed category set is read from content/categories/<slug>/_index.md and
author slugs from content/authors/<slug>/, so this script cannot drift from the
site the way a hard-coded list would.

Usage:
  python3 scripts/review_posts.py                      # every post
  python3 scripts/review_posts.py content/posts/x.md   # named posts
  python3 scripts/review_posts.py --changed-from origin/main
  python3 scripts/review_posts.py --strict --github    # CI annotations

  --changed-from REF  review only posts added/modified relative to REF
  --strict            fail on warnings as well as errors
  --github            emit ::error/::warning annotations and write a table
                      to $GITHUB_STEP_SUMMARY when it is set
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
POSTS = CONTENT / "posts"
STATIC = ROOT / "static"

REQUIRED = ["title", "date", "draft", "description", "categories", "tags", "authors", "readTime"]
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
MD_IMAGE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)")
BOX_CHARS = re.compile(r"[┌┐└┘├┤│─═╔╗╚╝▶▼]")
# Case-sensitive on purpose: "Todo List" and `todo_write` are real prose.
PLACEHOLDER = re.compile(r"\b(TODO|TBD|FIXME)\b|(?i:lorem ipsum)|待補|待填")
INLINE_CODE = re.compile(r"`[^`]*`")
ZH_NUMERALS = "一二三四五六七八九十"
SECTION = re.compile(r"^##\s+([一二三四五六七八九十]+)、")


def _slugs(directory: Path) -> set[str]:
    return {p.name for p in directory.iterdir() if (p / "_index.md").is_file()}


CATEGORIES = _slugs(CONTENT / "categories")
AUTHORS = _slugs(CONTENT / "authors")


@dataclass
class Finding:
    level: str  # "error" | "warning"
    line: int
    message: str


@dataclass
class Report:
    path: Path
    findings: list[Finding] = field(default_factory=list)

    def error(self, line: int, msg: str) -> None:
        self.findings.append(Finding("error", line, msg))

    def warn(self, line: int, msg: str) -> None:
        self.findings.append(Finding("warning", line, msg))


# ---------------------------------------------------------------- front matter

def _scalar(raw: str):
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [v.strip().strip("\"'") for v in inner.split(",")]
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    return raw


def parse_front_matter(text: str) -> tuple[dict | None, int]:
    """Parse the flat YAML subset posts use: scalars, inline and block lists.

    Returns (fields, body_start_line). PyYAML is not assumed to be installed
    on the runner, and the post archetype never nests, so a small parser is
    enough — and a nested value we do not understand is kept as a string, not
    silently dropped.
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None, 0
    fields: dict = {}
    key = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return fields, i + 1
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m:
            key, value = m.group(1), m.group(2)
            fields[key] = _scalar(value) if value.strip() else []
        elif key and re.match(r"^\s+-\s+", line) and isinstance(fields.get(key), list):
            fields[key].append(line.split("-", 1)[1].strip().strip("\"'"))
    return None, 0


def check_front_matter(r: Report, fm: dict) -> None:
    for k in REQUIRED:
        if k not in fm or fm[k] in ("", []):
            r.error(1, f"front matter: missing or empty `{k}`")

    date = fm.get("date")
    if isinstance(date, str) and date:
        try:
            datetime.fromisoformat(date.replace("Z", "+00:00"))
        except ValueError:
            r.error(1, f"front matter: `date` is not ISO 8601: {date!r}")

    if "draft" in fm and fm["draft"] not in ("true", "false"):
        r.error(1, f"front matter: `draft` must be true or false, got {fm['draft']!r}")

    cats = fm.get("categories")
    if isinstance(cats, list) and cats:
        if cats[0] != "all":
            r.error(1, 'front matter: `categories` must start with "all"')
        canonical = [c for c in cats if c != "all"]
        if not canonical:
            r.error(1, 'front matter: `categories` needs a canonical category besides "all"')
        for c in cats:
            if c not in CATEGORIES:
                r.error(1, f"front matter: category {c!r} is not in the closed set "
                           f"({', '.join(sorted(CATEGORIES))}); put it in `tags`")
        if len(canonical) > 3:
            r.warn(1, f"front matter: {len(canonical)} canonical categories; pick 1-3")
    elif "categories" in fm and not isinstance(cats, list):
        r.error(1, "front matter: `categories` must be a list")

    authors = fm.get("authors")
    if isinstance(authors, list):
        for a in authors:
            if a not in AUTHORS:
                r.error(1, f"front matter: author {a!r} has no content/authors/{a}/_index.md")

    tags = fm.get("tags")
    if "tags" in fm and not isinstance(tags, list):
        r.error(1, "front matter: `tags` must be a list")
    elif isinstance(tags, list) and len(set(t.lower() for t in tags)) != len(tags):
        r.warn(1, "front matter: duplicate tags")

    rt = fm.get("readTime")
    if isinstance(rt, str) and rt and not re.fullmatch(r"\d+ min", rt):
        r.error(1, f'front matter: `readTime` should look like "12 min", got {rt!r}')

    desc = fm.get("description")
    if isinstance(desc, str) and desc:
        if len(desc) < 20:
            r.warn(1, f"front matter: description is only {len(desc)} chars; it is the SEO snippet and card text")
        elif len(desc) > 300:
            r.warn(1, f"front matter: description is {len(desc)} chars; search engines truncate around 160")

    image = fm.get("image")
    if isinstance(image, str) and image and not re.match(r"https?://", image):
        if not (STATIC / image.lstrip("/")).is_file():
            r.error(1, f"front matter: `image` {image!r} is not a file under static/")


# ------------------------------------------------------------------------ body

def split_body(lines: list[str], start: int, r: Report) -> tuple[list[tuple[int, str]], list[list[str]]]:
    """Walk the body once; return (prose lines with numbers, code blocks).

    Fences close only on the same character with at least the opening length,
    which is CommonMark's rule — counting ``` occurrences mistakes a ````
    fence that shows a ``` example for two unbalanced blocks.
    """
    prose: list[tuple[int, str]] = []
    blocks: list[list[str]] = []
    open_fence: tuple[str, int, int, int] | None = None  # (char, length, indent, line)
    for n, line in enumerate(lines[start:], start=start + 1):
        m = FENCE.match(line)
        indent = len(line) - len(line.lstrip()) if m else 0
        if open_fence is None:
            if m:
                tok = m.group(1)
                open_fence = (tok[0], len(tok), indent, n)
                blocks.append([])
            else:
                prose.append((n, line))
        else:
            # A closer may sit at most 3 columns right of its opener; deeper
            # than that it is text inside the block (a nested example).
            if m and m.group(1)[0] == open_fence[0] and len(m.group(1)) >= open_fence[1] \
                    and indent <= open_fence[2] + 3 \
                    and not line.strip()[len(m.group(1)):].strip():
                open_fence = None
            else:
                blocks[-1].append(line)
    if open_fence:
        r.error(open_fence[3], "code fence opened here is never closed; the rest of the post renders as code")
    return prose, blocks


def check_body(r: Report, fm: dict, lines: list[str], start: int) -> None:
    prose, blocks = split_body(lines, start, r)

    last_level = 1
    for n, line in prose:
        h = HEADING.match(line)
        if h:
            level = len(h.group(1))
            if level == 1:
                r.warn(n, "H1 in the body; the title is already the page's H1, start sections at ##")
            elif level > last_level + 1:
                r.warn(n, f"heading jumps from H{last_level} to H{level}")
            last_level = level
        if PLACEHOLDER.search(INLINE_CODE.sub("", line)):
            r.warn(n, f"placeholder text left in prose: {line.strip()[:60]!r}")
        for src in MD_IMAGE.findall(line):
            if src.startswith("/") and not src.startswith("//"):
                if not (STATIC / src.split("#")[0].split("?")[0].lstrip("/")).is_file():
                    r.error(n, f"image {src!r} is not a file under static/")

    # readTime drift. The house convention (CLAUDE.md) is line-based —
    # 500 lines ≈ 18 min, 700 ≈ 23, 900 ≈ 28 — because diagrams and tables
    # read slower than their character count suggests. Only a 2x miss warns.
    minutes = (len(lines) - start) / 32
    rt = fm.get("readTime")
    if isinstance(rt, str) and re.fullmatch(r"\d+ min", rt) and minutes >= 2:
        stated = int(rt.split()[0])
        if stated > 2 * minutes + 2 or stated < minutes / 2 - 2:
            r.warn(1, f"readTime says {stated} min, content estimates ~{round(minutes)} min")

    check_series(r, fm, lines, prose, blocks)


def count_decisions(lines: list[str]) -> int:
    """Count 「為什麼選 X 不選 Y」 decisions, in any of the shapes posts use.

    Inside the section whose heading says 為什麼選 (up to the next ##): table
    data rows, ### sub-headings, and rows of a code-block table (lines that
    start flush-left after a ──── rule). Elsewhere: headings of the form
    「為什麼選 A 不選 B」.
    """
    count, in_section, after_rule = 0, False, False
    for i, line in enumerate(lines):
        if line.startswith("## "):
            in_section = "為什麼選" in line
            after_rule = False
            continue
        if not in_section:
            if line.startswith("#") and re.search(r"為什麼選.*(不選|而不是|vs)", line):
                count += 1
            continue
        s = line.strip()
        if s.startswith("|"):
            nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
            if not re.fullmatch(r"\|[\s:|-]+\|?", s) and not re.fullmatch(r"\|[\s:|-]+\|?", nxt):
                count += 1
        elif line.startswith("### "):
            count += 1
        elif re.fullmatch(r"[─━-]{10,}", s):
            after_rule = True
        elif after_rule and line and not line[0].isspace() and not FENCE.match(line):
            count += 1
        elif FENCE.match(line):
            after_rule = False
    return count


def check_series(r: Report, fm: dict, lines: list[str], prose, blocks) -> None:
    name = r.path.name
    tags = fm.get("tags") if isinstance(fm.get("tags"), list) else []
    cats = fm.get("categories") if isinstance(fm.get("categories"), list) else []
    total = len(lines)
    sections = [(n, SECTION.match(l).group(1)) for n, l in prose if SECTION.match(l)]
    diagrams = sum(1 for b in blocks if len(BOX_CHARS.findall("\n".join(b))) >= 8)
    decisions = count_decisions(lines)

    def house_rules(min_lines: int, max_lines: int, interview_format: bool) -> None:
        """Shared series checks. The phase section, the decision-table count and the
        line-count floor are the interview-prep house format (CLAUDE.md) and only apply
        when `interview_format` is set; diagrams and the 十 cap apply to every series."""
        if interview_format and total < min_lines:
            r.warn(1, f"{total} lines; the series target is {min_lines}-{max_lines}")
        for n, num in sections:
            if num not in ZH_NUMERALS:
                r.warn(n, f"section 「{num}」 exceeds the 十-section cap")
        if diagrams < 2:
            r.warn(1, f"{diagrams} ASCII box diagrams; the series standard is 2-4")
        if interview_format and not any("三個演進階段" in l for _, l in prose):
            r.warn(1, "no 「三個演進階段」 section")
        if interview_format and decisions < 4:
            r.warn(1, f"{decisions} 「為什麼選 X 不選 Y」 decisions; the standard is 4-6 with flip conditions")
        for n, l in prose:
            if "面試答題要點" in l and l.startswith("#"):
                r.warn(n, "「面試答題要點」 section was dropped from the standard format")

    # The "no Google" rule covers every interview-prep post: the fde-interview-guide series
    # by file name, and any other post that tags itself "Interview" (fde-core-concept today).
    if name.startswith("fde-interview-guide") or "Interview" in tags:
        for n, l in enumerate(lines, start=1):
            if re.search(r"google", l, re.I):
                r.warn(n, "interview posts must not mention Google (CLAUDE.md style rule)")
                break

    if name.startswith("fde-interview-guide"):
        house_rules(600, 900, interview_format=True)
        missing = [t for t in ("RKK", "Interview") if t not in tags]
        if missing:
            r.warn(1, f"interview post tags are missing {missing}")

    elif name.startswith("ai-eng-from-scratch"):
        house_rules(600, 900, interview_format=False)
        if "Interview" in tags:
            r.warn(1, 'ai-eng-from-scratch is not interview prep; drop the "Interview" tag')
        if "RKK" not in tags:
            r.warn(1, 'ai-eng-from-scratch tags should include "RKK"')
        if "面試" in str(fm.get("description", "")):
            r.warn(1, "description frames the post as interview material")

    if "finance" in cats:
        head = "\n".join(lines[:80])
        if not re.search(r"免責聲明|disclaimer|不構成.{0,6}投資建議|not investment advice", head, re.I):
            r.warn(1, "finance post has no disclaimer near the top (「不構成投資建議」)")
    if name.endswith("-10k-deep-dive-zh.md"):
        if "finance" not in cats:
            r.error(1, '10-K deep dive must be in the "finance" category')
        if not 400 <= total <= 700:
            r.warn(1, f"{total} lines; 10-K deep dives target 450-600")


# ------------------------------------------------------------------------- run

def review(path: Path) -> Report:
    r = Report(path)
    text = path.read_text(encoding="utf-8")
    fm, start = parse_front_matter(text)
    if fm is None:
        r.error(1, "no YAML front matter (--- ... ---) at the top of the file")
        return r
    check_front_matter(r, fm)
    check_body(r, fm, text.split("\n"), start)
    return r


def changed_posts(ref: str) -> list[Path]:
    out = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=AMR", f"{ref}...HEAD", "--", "content/posts/"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout
    return [ROOT / p for p in out.split() if p.endswith(".md")]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", type=Path)
    ap.add_argument("--changed-from", metavar="REF")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--github", action="store_true")
    args = ap.parse_args()

    if args.changed_from:
        paths = changed_posts(args.changed_from)
    elif args.paths:
        paths = [p.resolve() for p in args.paths]
    else:
        paths = sorted(POSTS.glob("*.md"))
    paths = [p for p in paths if p.name != "_index.md" and p.is_file()]
    if not paths:
        print("review_posts: no posts to review")
        return 0

    reports = [review(p) for p in paths]
    errors = sum(f.level == "error" for r in reports for f in r.findings)
    warnings = sum(f.level == "warning" for r in reports for f in r.findings)

    for r in reports:
        rel = r.path.relative_to(ROOT)
        for f in sorted(r.findings, key=lambda f: (f.level != "error", f.line)):
            if args.github:
                print(f"::{f.level} file={rel},line={f.line}::{f.message}")
            else:
                print(f"{rel}:{f.line}: {f.level}: {f.message}")

    summary = f"review_posts: {len(reports)} post(s), {errors} error(s), {warnings} warning(s)"
    print(summary)

    if args.github and os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as out:
            out.write(f"### Post review\n\n{summary}\n\n")
            flagged = [r for r in reports if r.findings]
            if flagged:
                out.write("| post | errors | warnings |\n|---|---|---|\n")
                for r in flagged:
                    e = sum(f.level == "error" for f in r.findings)
                    out.write(f"| `{r.path.name}` | {e} | {len(r.findings) - e} |\n")

    return 1 if errors or (args.strict and warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
