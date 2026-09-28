#!/usr/bin/env python3
"""Mechanical audit of every post under content/posts/ against the CLAUDE.md standards.

Usage:  python3 scripts/audit_content.py [REPO_ROOT] [OUT_DIR]
        (defaults: the repo this script lives in, and ./.content-audit/)

Writes to OUT_DIR:
  audit.json  - one record per post
  audit.tsv   - flat table for eyeballing
  summary.txt - aggregate counts (also printed)
and regenerates docs/content-audit/per-post-checklist.md in the repo.

It only reads content; it never edits a post. The qualitative per-post review
in docs/content-audit/ was built on top of this output.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent).resolve()
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else ROOT / ".content-audit").resolve()
OUT.mkdir(parents=True, exist_ok=True)
POSTS = ROOT / "content" / "posts"

VALID_CATEGORIES = {p.parent.name for p in (ROOT / "content" / "categories").glob("*/_index.md")}
VALID_AUTHORS = {p.parent.name for p in (ROOT / "content" / "authors").glob("*/_index.md")}
# Only this blog's own sub-path; other projects on yennj12.js.org (/InvestSkill/, …) are fine.
BASEURL_RE = re.compile(r"yennj12\.js\.org/yennj12_blog_V4|/yennj12_blog_V4/")
BOX_CHARS = re.compile(r"[┌┐└┘├┤┬┴┼─│▶▼◀▲╔╗╚╝═║╠╣╦╩╬━┃┏┓┗┛]")
CJK = re.compile(r"[一-鿿]")
CN_NUM_H2 = re.compile(r"^##\s*(一|二|三|四|五|六|七|八|九|十|十一|十二|十三|十四|十五|十六|十七|十八|十九|二十)[、.．\s]")
# Case-sensitive on purpose: "Todo" is Claude Code's todo list, "xxx" an example value.
PLACEHOLDER = re.compile(r"\b(?:TODO|TBD|FIXME)\b|lorem ipsum|待補|待填")
MD_LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
FENCE = re.compile(r"^\s*(```+|~~~+)")

ALL_SLUGS = {p.stem for p in POSTS.glob("*.md")}
ALL_TAGS = Counter()


def series_of(name: str) -> str:
    s = re.sub(r"-(part|phase)\d+.*$", "", name)
    s = re.sub(r"-\d+-.*$", "", s)
    s = re.sub(r"-zh$", "", s)
    if re.search(r"-\d{4}-10k-deep-dive", name):
        return "10k-deep-dive"
    if name.startswith("stock-analysis-"):
        return "stock-analysis"
    if name.startswith("nvidia-"):
        return "nvidia-blog-translation"
    return s


def split_front_matter(text: str):
    """Return (front_matter_dict, body, error). Front matter ends at the first bare '---' line."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None, text, "no front matter"
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return None, text, "unterminated front matter"
    body = "\n".join(lines[end + 1 :])
    try:
        fm = yaml.safe_load("\n".join(lines[1:end])) or {}
    except Exception as e:  # noqa: BLE001
        return None, body, f"yaml error: {e}"
    return fm, body, None


def parse_readtime(v) -> int | None:
    if v is None:
        return None
    m = re.search(r"(\d+)", str(v))
    return int(m.group(1)) if m else None


def expected_readtime(lines: int) -> int:
    # 500L≈18min, 700L≈23min, 900L≈28min  -> ~2.5 min per 100 lines + 5.5
    return round(5.5 + lines * 0.025)


def fenced_blocks(lines: list[str]):
    """Return ([(start, end, info, content)], unclosed) using CommonMark closing rules.

    A fence closes only on the same character, at least as long as the opener and
    with no info string, so a ```` block that shows ``` inside it stays one block.
    """
    blocks = []
    opener = None
    for i, ln in enumerate(lines):
        m = FENCE.match(ln)
        if not m:
            continue
        mark = m.group(1)
        rest = ln.strip()[len(mark) :].strip()
        if opener is None:
            opener = (i, mark, rest)
        elif mark[0] == opener[1][0] and len(mark) >= len(opener[1]) and not rest:
            start = opener[0]
            blocks.append((start, i, opener[2], "\n".join(lines[start + 1 : i])))
            opener = None
    return blocks, opener is not None


def audit(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    fm, body, fm_err = split_front_matter(text)
    fm = fm or {}
    name = path.stem
    rec: dict = {"file": path.name, "slug": name, "series": series_of(name), "is_zh": name.endswith("-zh")}
    rec["fm_error"] = fm_err

    # ---- front matter ----
    rec["title"] = fm.get("title")
    rec["date"] = str(fm.get("date")) if fm.get("date") is not None else None
    rec["draft"] = bool(fm.get("draft", False))
    rec["has_description"] = bool(fm.get("description"))
    rec["has_summary"] = bool(fm.get("summary"))
    rec["description_len"] = len(str(fm.get("description") or ""))
    cats = fm.get("categories") or []
    if isinstance(cats, str):
        cats = [cats]
    rec["categories"] = cats
    rec["invalid_categories"] = [c for c in cats if c not in VALID_CATEGORIES]
    rec["missing_all_category"] = "all" not in cats
    rec["only_all_category"] = cats == ["all"]
    rec["n_canonical_categories"] = len([c for c in cats if c != "all"])
    tags = fm.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    rec["tags"] = tags
    ALL_TAGS.update(tags)
    rec["n_tags"] = len(tags)
    rec["has_tag_RKK"] = "RKK" in tags
    rec["has_tag_Interview"] = "Interview" in tags
    rec["has_tag_Google"] = any("google" in str(t).lower() for t in tags)
    authors = fm.get("authors") or fm.get("author") or []
    if isinstance(authors, str):
        authors = [authors]
    rec["authors"] = authors
    rec["invalid_authors"] = [a for a in authors if a not in VALID_AUTHORS]
    rec["readTime_raw"] = fm.get("readTime")
    rec["readTime_min"] = parse_readtime(fm.get("readTime"))
    rec["has_image"] = bool(fm.get("image"))
    rec["extra_fm_keys"] = sorted(set(fm) - {"title", "date", "draft", "description", "summary", "categories", "tags", "authors", "readTime", "image", "imageAlt", "weight", "series", "keywords", "lastmod", "slug", "aliases", "toc", "featured", "author"})

    # ---- body ----
    lines = body.split("\n")
    rec["lines"] = len(lines)
    rec["chars"] = len(body)

    # fenced blocks
    fences, rec["unclosed_fence"] = fenced_blocks(lines)
    rec["code_blocks"] = len(fences)
    rec["ascii_diagrams"] = sum(1 for f in fences if len(BOX_CHARS.findall(f[3])) >= 20)
    rec["code_lines"] = sum(f[1] - f[0] - 1 for f in fences)
    rec["code_ratio"] = round(rec["code_lines"] / max(rec["lines"], 1), 2)
    rec["longest_code_block"] = max((f[1] - f[0] - 1 for f in fences), default=0)
    rec["code_langs"] = sorted({f[2].split()[0] for f in fences if f[2]})

    # headings (outside fences)
    in_code = set()
    for start, end, _, _ in fences:
        in_code.update(range(start, end + 1))
    prose_lines = [ln for i, ln in enumerate(lines) if i not in in_code]
    prose = "\n".join(prose_lines)

    # Language is judged on prose only: a Chinese post full of English code is still Chinese.
    rec["cjk_chars"] = len(CJK.findall(prose))
    latin_words = len(re.findall(r"[A-Za-z]{2,}", prose))
    rec["latin_words"] = latin_words
    rec["lang_guess"] = "zh" if rec["cjk_chars"] > latin_words * 0.6 else "en"
    rec["lang_mismatch"] = (rec["is_zh"] and rec["lang_guess"] == "en") or ((not rec["is_zh"]) and rec["lang_guess"] == "zh")
    h1s = [l for l in prose_lines if re.match(r"^#\s", l)]
    h2s = [l for l in prose_lines if re.match(r"^##\s", l)]
    h3s = [l for l in prose_lines if re.match(r"^###\s", l)]
    rec["h1_in_body"] = len(h1s)
    rec["h2_count"] = len(h2s)
    rec["h3_count"] = len(h3s)
    rec["h2_cn_numeral"] = sum(1 for l in h2s if CN_NUM_H2.match(l))
    dup = [h for h, c in Counter(h.strip() for h in h2s + h3s).items() if c > 1]
    rec["duplicate_headings"] = dup[:5]
    rec["max_cn_numeral"] = 0
    order = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十"]
    for l in h2s:
        m = CN_NUM_H2.match(l)
        if m:
            rec["max_cn_numeral"] = max(rec["max_cn_numeral"], order.index(m.group(1)) + 1)
    rec["h2_titles"] = [re.sub(r"^##\s*", "", h).strip() for h in h2s]

    # standard-content markers
    rec["has_three_phases"] = "三個演進階段" in body or "三個階段" in body or "演進階段" in body
    rec["why_x_not_y_count"] = len(re.findall(r"為什麼選|為何選|不選\s*[A-Za-z]", body))
    rec["has_why_x_not_y_section"] = any("為什麼選" in h or "不選" in h for h in rec["h2_titles"])
    rec["has_interview_answer_section"] = "面試答題要點" in body
    rec["has_interview_scenario"] = "面試情境" in body
    rec["has_system_effects"] = any("系統效應" in h for h in rec["h2_titles"])
    rec["has_series_nav"] = bool(re.search(r"系列導航|系列文章|系列目錄|Series Navigation|本系列|上一篇|下一篇|← |→ Part|Part \d+", body[-4000:], re.I))
    rec["opening_quote_lines"] = len([l for l in prose_lines[:40] if l.startswith(">")])
    google_hits = re.findall(r"Google", body)
    rec["google_mentions"] = len(google_hits)
    rec["placeholders"] = PLACEHOLDER.findall(re.sub(r"`[^`\n]*`", "", "\n".join(l for l in prose_lines if not l.lstrip().startswith(">"))))[:5]
    rec["hardcoded_baseurl"] = len(BASEURL_RE.findall(body))
    rec["numbers_density"] = round(len(re.findall(r"\d+(?:\.\d+)?\s*(?:ms|%|QPS|MAU|\$|USD|GB|MB|TB|秒|ms|美元|萬|億|K\b|M\b)", body)) / max(rec["lines"], 1) * 100, 1)
    rec["tables"] = len([l for l in prose_lines if re.match(r"^\s*\|.*\|\s*$", l)])
    rec["images"] = len(re.findall(r"!\[[^\]]*\]\(", body))
    rec["external_links"] = len(re.findall(r"\]\(https?://", body))

    # internal links
    internal = []
    dead = []
    # Scan prose only: links inside fenced blocks or `inline code` are examples, not links.
    for m in MD_LINK.finditer(re.sub(r"`[^`\n]*`", "", prose)):
        href = m.group(2)
        if href.startswith("http") or href.startswith("#") or href.startswith("mailto:"):
            continue
        internal.append(href)
        h = href.split("#")[0].strip("/")
        if h.startswith("posts/"):
            slug = h[len("posts/") :]
            if slug not in ALL_SLUGS:
                dead.append(href)
        elif h.startswith("tags/") or h.startswith("categories/") or h.startswith("authors/") or h in ("", "about", "posts", "posts-list"):
            pass
        elif h.startswith("images/"):
            if not (ROOT / "static" / h).exists():
                dead.append(href)
        elif h and "/" not in h and not h.endswith(".md"):
            # bare slug -> /posts/<slug>
            if h not in ALL_SLUGS:
                dead.append(href)
        elif h.endswith(".md"):
            dead.append(href)
    rec["internal_links"] = len(internal)
    rec["dead_internal_links"] = dead
    rec["dead_internal_links_count"] = len(dead)

    # readTime calibration
    # Outside the two standard series, code-block lines count half: readers skim code dumps.
    rec["readTime_lines"] = rec["lines"] if rec["series"] in ("fde-interview-guide", "ai-eng-from-scratch") else round(rec["lines"] - rec["code_lines"] / 2)
    if rec["readTime_min"] is not None:
        exp = expected_readtime(rec["readTime_lines"])
        rec["readTime_expected"] = exp
        rec["readTime_delta"] = rec["readTime_min"] - exp
    else:
        rec["readTime_expected"] = expected_readtime(rec["readTime_lines"])
        rec["readTime_delta"] = None

    # ending: does the file end mid-sentence / short?
    tail = prose.strip()[-200:]
    rec["ends_with_heading"] = bool(re.search(r"\n#{1,6}\s[^\n]*$", prose.strip()))
    rec["tail"] = tail[-120:].replace("\n", " ")
    return rec


records = [audit(p) for p in sorted(POSTS.glob("*.md"))]

(OUT / "audit.json").write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")

cols = [
    "file", "series", "lines", "readTime_min", "readTime_expected", "readTime_delta", "has_description", "has_summary",
    "categories", "invalid_categories", "n_tags", "has_tag_RKK", "has_tag_Interview", "authors", "invalid_authors",
    "ascii_diagrams", "code_blocks", "code_ratio", "h2_count", "h2_cn_numeral", "max_cn_numeral", "has_three_phases",
    "why_x_not_y_count", "has_interview_answer_section", "has_interview_scenario", "has_series_nav", "google_mentions",
    "dead_internal_links_count", "hardcoded_baseurl", "lang_mismatch", "draft", "date", "unclosed_fence", "h1_in_body",
    "duplicate_headings", "placeholders", "tables", "numbers_density", "opening_quote_lines", "has_image",
]
with (OUT / "audit.tsv").open("w", encoding="utf-8") as fh:
    fh.write("\t".join(cols) + "\n")
    for r in records:
        fh.write("\t".join(json.dumps(r.get(c), ensure_ascii=False) if not isinstance(r.get(c), (str, int, float, bool, type(None))) else str(r.get(c)) for c in cols) + "\n")

# ---- summary ----
S = []


def line(s=""):
    S.append(s)

line(f"posts: {len(records)}")
line(f"valid categories: {sorted(VALID_CATEGORIES)}")
line(f"valid authors: {sorted(VALID_AUTHORS)}")
line()
def count(pred, label):
    hits = [r for r in records if pred(r)]
    line(f"{label}: {len(hits)}")
    return hits

count(lambda r: r["fm_error"], "front matter errors")
count(lambda r: r["draft"], "drafts")
count(lambda r: not r["has_description"], "missing description")
count(lambda r: not r["has_description"] and not r["has_summary"], "missing description AND summary")
count(lambda r: r["invalid_categories"], "invalid categories")
count(lambda r: r["missing_all_category"], "missing 'all' category")
count(lambda r: r["only_all_category"], "only 'all' category")
count(lambda r: r["n_canonical_categories"] > 3, ">3 canonical categories")
count(lambda r: r["invalid_authors"], "invalid authors")
count(lambda r: not r["authors"], "no authors")
count(lambda r: r["readTime_min"] is None, "missing readTime")
count(lambda r: r["readTime_delta"] is not None and abs(r["readTime_delta"]) >= 8, "readTime off by >=8 min vs line-count rule")
count(lambda r: r["dead_internal_links_count"] > 0, "posts with dead internal links")
line(f"  total dead internal links: {sum(r['dead_internal_links_count'] for r in records)}")
count(lambda r: r["hardcoded_baseurl"] > 0, "hardcoded baseURL in body")
count(lambda r: r["lang_mismatch"], "filename/body language mismatch")
count(lambda r: r["unclosed_fence"], "unclosed code fence")
count(lambda r: r["h1_in_body"] > 0, "H1 in body")
count(lambda r: r["duplicate_headings"], "duplicate headings")
count(lambda r: r["placeholders"], "placeholders (TODO/TBD/待補)")
count(lambda r: r["has_interview_answer_section"], "has 面試答題要點 section")
count(lambda r: r["lines"] < 200, "very short (<200 lines)")
count(lambda r: r["lines"] < 400, "short (<400 lines)")
count(lambda r: r["code_ratio"] > 0.6, "code-heavy (>60% lines in fences)")
count(lambda r: r["ascii_diagrams"] == 0, "no ASCII diagram")
count(lambda r: r["n_tags"] < 3, "fewer than 3 tags")
count(lambda r: r["n_tags"] > 12, "more than 12 tags")
count(lambda r: r["has_image"], "has custom og image")
count(lambda r: r["extra_fm_keys"], "non-standard front matter keys")
line()
line("categories usage:")
cc = Counter(c for r in records for c in r["categories"])
for k, v in cc.most_common():
    line(f"  {k}: {v}")
line()
line("series overview (count, avg lines, min lines, missing description, dead links, no diagram):")
by = defaultdict(list)
for r in records:
    by[r["series"]].append(r)
for s, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
    line(f"  {s:45s} n={len(rs):3d} avgL={sum(r['lines'] for r in rs)//len(rs):4d} minL={min(r['lines'] for r in rs):4d} nodesc={sum(not r['has_description'] for r in rs):3d} dead={sum(r['dead_internal_links_count'] for r in rs):3d} nodiag={sum(r['ascii_diagrams']==0 for r in rs):3d}")
line()
line("interview-series 'Google' mentions (fde-interview-guide, fde-core-concept, ai-fde-essential-guide):")
for r in records:
    if r["series"] in ("fde-interview-guide", "fde-core-concept", "ai-fde-essential-guide") and (r["google_mentions"] or r["has_tag_Google"]):
        line(f"  {r['file']}: body={r['google_mentions']} tag={r['has_tag_Google']}")
line()
line("fde-interview-guide / ai-eng-from-scratch checklist failures:")
for r in records:
    if r["series"] in ("fde-interview-guide", "ai-eng-from-scratch"):
        fails = []
        if r["lines"] < 600: fails.append(f"lines={r['lines']}")
        if not (2 <= r["ascii_diagrams"] <= 6): fails.append(f"diagrams={r['ascii_diagrams']}")
        if not r["has_three_phases"]: fails.append("no-3phases")
        if r["why_x_not_y_count"] < 4: fails.append(f"whyXY={r['why_x_not_y_count']}")
        if r["has_interview_answer_section"]: fails.append("has-面試答題要點")
        if not r["has_tag_RKK"]: fails.append("no-RKK")
        if r["series"] == "fde-interview-guide" and not r["has_tag_Interview"]: fails.append("no-Interview-tag")
        if r["series"] == "ai-eng-from-scratch" and r["has_tag_Interview"]: fails.append("has-Interview-tag")
        if r["series"] == "fde-interview-guide" and not r["has_interview_scenario"]: fails.append("no-面試情境")
        if r["max_cn_numeral"] > 10: fails.append(f"sections>{r['max_cn_numeral']}")
        if r["readTime_delta"] is not None and abs(r["readTime_delta"]) >= 6: fails.append(f"readTimeΔ={r['readTime_delta']}")
        if not r["has_series_nav"]: fails.append("no-series-nav")
        if r["dead_internal_links_count"]: fails.append(f"dead={r['dead_internal_links_count']}")
        if fails:
            line(f"  {r['file']}: " + ", ".join(fails))
line()
line("10-K posts checklist (450–600 lines, finance category, 10-K tag):")
for r in records:
    if r["series"] == "10k-deep-dive":
        fails = []
        if not (400 <= r["lines"] <= 700): fails.append(f"lines={r['lines']}")
        if "finance" not in r["categories"]: fails.append("no-finance-cat")
        if not any("10-k" in str(t).lower() for t in r["tags"]): fails.append("no-10-K-tag")
        if not r["has_description"]: fails.append("no-desc")
        line(f"  {r['file']}: h2={r['h2_count']} lines={r['lines']} " + (", ".join(fails) if fails else "ok"))
line()
line("tags used only once (candidates to consolidate):")
singles = sorted(t for t, c in ALL_TAGS.items() if c == 1)
line(f"  {len(singles)} of {len(ALL_TAGS)} tags — " + ", ".join(singles[:80]) + (" …" if len(singles) > 80 else ""))
line()
line("tag case/spelling near-duplicates:")
norm = defaultdict(set)
for t in ALL_TAGS:
    norm[re.sub(r"[^a-z0-9一-鿿]", "", str(t).lower())].add(t)
for k, vs in sorted(norm.items()):
    if len(vs) > 1:
        line(f"  {sorted(vs)}")
line()
line("dead internal links by target (top 40):")
dt = Counter(l for r in records for l in r["dead_internal_links"])
for k, v in dt.most_common(40):
    line(f"  {v:3d}  {k}")

(OUT / "summary.txt").write_text("\n".join(S), encoding="utf-8")
print("\n".join(S))


# ---- per-post Markdown checklist (docs/content-audit/per-post-checklist.md) ----
INTERVIEW_SERIES = ("fde-interview-guide", "fde-core-concept", "ai-fde-essential-guide")
STANDARD_SERIES = ("fde-interview-guide", "ai-eng-from-scratch")


def issues(r: dict) -> list[str]:
    out = []
    if not r["has_description"]:
        out.append("no `description`")
    if r["invalid_authors"] or not r["authors"]:
        out.append(f"author `{r['authors'][0] if r['authors'] else '∅'}` has no profile")
    if r["readTime_min"] is None:
        out.append("no `readTime`")
    elif abs(r["readTime_delta"]) >= 8:
        out.append(f"readTime {r['readTime_min']}m vs ~{r['readTime_expected']}m")
    if r["dead_internal_links_count"]:
        out.append(f"{r['dead_internal_links_count']} dead internal link(s)")
    if r["has_interview_answer_section"]:
        out.append("has dropped 面試答題要點")
    if r["n_canonical_categories"] > 3:
        out.append(f"{r['n_canonical_categories']} categories (max 3)")
    if r["n_tags"] > 12:
        out.append(f"{r['n_tags']} tags")
    if r["series"] in INTERVIEW_SERIES and r["has_tag_Google"]:
        out.append("`Google` tag")
    if r["series"] in INTERVIEW_SERIES and not r["has_tag_RKK"]:
        out.append("no `RKK` tag")
    if r["series"] == "ai-eng-from-scratch" and r["has_tag_Interview"]:
        out.append("`Interview` tag on non-interview series")
    if r["series"] in STANDARD_SERIES:
        if r["lines"] < 600:
            out.append(f"{r['lines']} lines (<600)")
        if not r["has_three_phases"]:
            out.append("no 三個演進階段")
        if r["why_x_not_y_count"] < 4:
            out.append(f"{r['why_x_not_y_count']}× 為什麼選 X 不選 Y (<4)")
        if r["max_cn_numeral"] > 10:
            out.append(f"sections run to {r['max_cn_numeral']} (cap 十)")
    if r["h1_in_body"]:
        out.append("H1 inside body")
    if any(h.startswith("### ╔") for h in r["duplicate_headings"]):
        out.append("╔══╗ box written as `###` headings")
    if r["lang_mismatch"]:
        out.append("`-zh` file is mostly English" if r["is_zh"] else "non-`-zh` file is mostly Chinese")
    if "\xa0" in r["file"]:
        out.append("non-breaking spaces in filename")
    if r["lines"] < 200:
        out.append(f"only {r['lines']} lines")
    if r["placeholders"]:
        out.append("placeholder text (" + ", ".join(sorted(set(r["placeholders"]))) + ")")
    return out


def _order(r: dict):
    m = re.search(r"(?:part|phase|concept-)(\d+)", r["file"])
    return (int(m.group(1)) if m else 0, r["file"])


groups = defaultdict(list)
for r in records:
    groups[r["series"]].append(r)
md = [
    "# Per-post mechanical checklist",
    "",
    "Generated by `python3 scripts/audit_content.py`. Regenerate it rather than editing by hand.",
    "Each row lists only the rule-level problems a script can detect; the qualitative review of",
    "the same post is in `reviews/`. A dash means the post passed every mechanical check.",
    "",
    "readTime is compared with the CLAUDE.md calibration (500 lines ≈ 18 min, 700 ≈ 23, 900 ≈ 28,",
    "extrapolated linearly; outside the two standard series code-block lines count half) and",
    "flagged at 8 minutes or more off. Series-standard checks",
    "(600 lines, 三個演進階段, 為什麼選 X 不選 Y, section cap) run only on fde-interview-guide and",
    "ai-eng-from-scratch, the two series CLAUDE.md defines them for.",
    "",
]
multi = sorted((s for s in groups if len(groups[s]) > 1), key=lambda s: (-len(groups[s]), s))
for s in multi:
    md += [f"## {s} ({len(groups[s])})", "", "| Post | Lines | Issues |", "|---|---:|---|"]
    for r in sorted(groups[s], key=_order):
        i = issues(r)
        md.append(f"| `{r['file']}` | {r['lines']} | {'; '.join(i) if i else '—'} |")
    md.append("")
md += ["## Standalone posts", "", "| Post | Lines | Issues |", "|---|---:|---|"]
for s in sorted(s for s in groups if len(groups[s]) == 1):
    r = groups[s][0]
    i = issues(r)
    md.append(f"| `{r['file']}` | {r['lines']} | {'; '.join(i) if i else '—'} |")
(ROOT / "docs" / "content-audit" / "per-post-checklist.md").write_text("\n".join(md) + "\n", encoding="utf-8")
print(f"\nclean posts (no mechanical issue): {sum(not issues(r) for r in records)} of {len(records)}")
