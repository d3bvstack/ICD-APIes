#!/usr/bin/env python3
"""Conformance checker for the Spanish ICD-API documentation.

The oracle is the vendored OpenAPI/Swagger snapshot of the WHO ICD-API
(https://id.who.int/swagger/v2/swagger.json) plus the facts published in the
official ICD-API documentation pages.

It checks, in order:
  1.  both deliverables exist and are non-trivial;
  2.  every endpoint path quoted in the docs exists in the spec (no invented
      routes) and every operational endpoint of the spec is covered;
  3.  every query/header parameter quoted in the docs exists in the spec for
      that endpoint (no invented parameters);
  4.  the mandatory request headers and the Spanish language code are
      documented;
  5.  the Spanish support matrix matches the official Supported Classifications
      table exactly;
  6.  every shell / Python / JavaScript / JSON sample parses;
  7.  the HTML deliverable is structurally accessible (WCAG 2.2 AA oriented
      structural checks + real contrast computation on the shipped palette).

Exit code 0 = all checks pass, 1 = at least one failure.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC_PATH = HERE / "icd-api-swagger.json"
MD_PATH = HERE / "icd-api-es.md"
HTML_PATH = HERE / "icd-api-es.html"

FAILURES: list[str] = []
PASSES: list[str] = []


def check(condition: bool, message: str, ok_message: str = "") -> bool:
    if condition:
        PASSES.append(ok_message or message)
        return True
    FAILURES.append(message)
    return False


# --------------------------------------------------------------------------
# Load the oracle
# --------------------------------------------------------------------------
if not SPEC_PATH.exists():
    print(f"FATAL: missing oracle spec {SPEC_PATH}", file=sys.stderr)
    sys.exit(1)

SPEC = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
SPEC_PATHS: dict[str, dict] = SPEC["paths"]
SPEC_SCHEMAS: dict[str, dict] = SPEC["components"]["schemas"]


def spec_params(path: str) -> set[str]:
    """All parameter names (path + query + header) declared for an endpoint."""
    names: set[str] = set()
    for method, op in SPEC_PATHS.get(path, {}).items():
        if method not in ("get", "post", "put", "delete", "patch"):
            continue
        for p in op.get("parameters", []):
            if "$ref" in p:
                p = SPEC["components"]["parameters"][p["$ref"].split("/")[-1]]
            if "name" in p:
                names.add(p["name"])
    return names


def spec_param_defaults(path: str) -> dict[str, object]:
    out: dict[str, object] = {}
    for method, op in SPEC_PATHS.get(path, {}).items():
        if method not in ("get", "post", "put", "delete", "patch"):
            continue
        for p in op.get("parameters", []):
            if "$ref" in p:
                p = SPEC["components"]["parameters"][p["$ref"].split("/")[-1]]
            if "name" in p:
                out[p["name"]] = p.get("default")
    return out


def all_spec_param_names() -> set[str]:
    names: set[str] = set()
    for path in SPEC_PATHS:
        names |= spec_params(path)
    return names


PLACEHOLDER_VALUE_RULES = {
    # A literal written in a doc path is only a legitimate concrete value for a
    # spec placeholder if it looks like one. Without this, "/icd/entity/foo"
    # would be accepted as a concrete value of {id} and invented routes would
    # slip through.
    "id": re.compile(r"^\d+$"),
    "linearizationname": re.compile(r"^(mms|icf)$"),
    "releaseId": re.compile(r"^\d{4}(-\d{2})?$"),
    "residual": re.compile(r"^(other|unspecified)$"),
    "code": re.compile(r"^[A-Za-z0-9%&/.\-]+$"),
}


def compatible_spec_paths(doc_path: str) -> list[str]:
    """Spec paths that a human-written doc path can legitimately refer to.

    Alignment is positional: a doc segment that is a literal is accepted as a
    concrete value for the corresponding spec placeholder (e.g. `mms` for
    `{linearizationname}`) only if it looks like a legal value for that
    placeholder; a doc segment that is a placeholder must carry the same
    placeholder name as the spec, unless it is snake_case -- that form denotes
    a language-level interpolation such as a Python f-string
    (`/icd/release/11/{release_id}/mms`) rather than an API placeholder.
    """
    doc_segs = doc_path.strip("/").split("/")
    hits = []
    for spec_path in SPEC_PATHS:
        spec_segs = spec_path.strip("/").split("/")
        if len(doc_segs) != len(spec_segs):
            continue
        ok = True
        for d, s in zip(doc_segs, spec_segs):
            if s.startswith("{") and s.endswith("}"):
                name = s[1:-1]
                if d.startswith("{") and d.endswith("}"):
                    if d == s:
                        continue  # same placeholder name
                    if "_" in d:
                        continue  # language-level interpolation, position matches
                    ok = False
                    break
                else:
                    # A literal standing in for a placeholder.
                    rule = PLACEHOLDER_VALUE_RULES.get(name)
                    if rule is not None and not rule.match(d):
                        ok = False
                        break
                    continue
            else:
                if d != s:
                    ok = False
                    break
        if ok:
            hits.append(spec_path)
    return hits


# --------------------------------------------------------------------------
# Markdown helpers
# --------------------------------------------------------------------------
FENCE_RE = re.compile(r"^```([A-Za-z0-9_+-]*)\s*$")


def md_code_blocks(md: str) -> list[tuple[str, str]]:
    """Return (language, source) for every fenced block."""
    blocks: list[tuple[str, str]] = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        m = FENCE_RE.match(lines[i])
        if not m:
            i += 1
            continue
        lang = m.group(1).lower()
        i += 1
        buf: list[str] = []
        while i < len(lines) and not FENCE_RE.match(lines[i]):
            buf.append(lines[i])
            i += 1
        blocks.append((lang, "\n".join(buf)))
    return blocks


def md_tables(md: str) -> list[list[list[str]]]:
    """Return every markdown table as a list of rows (list of cells)."""
    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    for line in md.splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|") and len(stripped) > 1:
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                continue  # separator row
            current.append(cells)
        else:
            if current:
                tables.append(current)
                current = []
    if current:
        tables.append(current)
    return tables


def cell_code(cell: str) -> str | None:
    m = re.fullmatch(r"`([^`]+)`", cell.strip())
    return m.group(1) if m else None


# --------------------------------------------------------------------------
# 1. deliverables exist
# --------------------------------------------------------------------------
md = MD_PATH.read_text(encoding="utf-8") if MD_PATH.exists() else ""
html = HTML_PATH.read_text(encoding="utf-8") if HTML_PATH.exists() else ""

check(
    MD_PATH.exists() and len(md) > 8000,
    f"FAIL: {MD_PATH.name} is missing or too short (found {len(md)} chars, need > 8000)",
    f"OK: {MD_PATH.name} exists ({len(md)} chars)",
)
check(
    HTML_PATH.exists() and len(html) > 8000,
    f"FAIL: {HTML_PATH.name} is missing or too short (found {len(html)} chars, need > 8000)",
    f"OK: {HTML_PATH.name} exists ({len(html)} chars)",
)

if not md or not html:
    print("\n".join(f"  {f}" for f in FAILURES))
    print(f"\n{len(FAILURES)} check(s) failed - documentation not written yet.")
    sys.exit(1)

# --------------------------------------------------------------------------
# 2. endpoint coverage: no invented routes, no missing operational routes
# --------------------------------------------------------------------------
doc_path_re = re.compile(r"/icd/(?:release|entity)[A-Za-z0-9/{}_.-]*")
raw_paths = doc_path_re.findall(md)

# A path written with a trailing ellipsis ("/icd/release/11/...") is a family
# reference: it must still resolve to at least one real endpoint. Classify it
# before stripping trailing punctuation, otherwise the dots are lost.
family_refs = set()
doc_paths = set()
for raw in raw_paths:
    candidate = raw.rstrip("`")
    if candidate.endswith(("...", "…")):
        family_refs.add(candidate)
    else:
        doc_paths.add(candidate.rstrip(".,;)`"))

invented = []
for p in sorted(doc_paths):
    if not compatible_spec_paths(p):
        invented.append(p)
for p in sorted(family_refs):
    prefix = p.rstrip(".…").rstrip("/")
    if not any(spec_path.startswith(prefix) for spec_path in SPEC_PATHS):
        invented.append(p)
check(
    not invented,
    "FAIL: endpoint path(s) quoted in the docs that do not exist in the OpenAPI spec: "
    + ", ".join(invented),
    f"OK: all {len(doc_paths) + len(family_refs)} endpoint path(s) quoted in the docs exist in the spec",
)

# every operational endpoint of the spec must be mentioned somewhere
missing = []
for spec_path in SPEC_PATHS:
    # concrete reference form: the spec path with placeholders as <name>
    probe = re.sub(r"\{([^}]+)\}", r"\1", spec_path)
    if probe.lower() in md.lower().replace("{", "").replace("}", "").replace(" ", ""):
        continue
    if spec_path in md:
        continue
    # accept a doc reference where the placeholder was replaced by a literal
    segments = spec_path.strip("/").split("/")
    variants = set()
    for ph in ("releaseId", "linearizationname", "id", "residual", "code"):
        variants.add(spec_path.replace("{" + ph + "}", ph))
    variants.add(re.sub(r"\{[^}]+\}", "mms", spec_path))
    if any(v in md for v in variants):
        continue
    missing.append(spec_path)
check(
    not missing,
    "FAIL: spec endpoint(s) never documented: " + ", ".join(missing),
    f"OK: all {len(SPEC_PATHS)} spec endpoints are covered by the documentation",
)

# --------------------------------------------------------------------------
# 3. parameter tables: no invented parameters
# --------------------------------------------------------------------------
GLOBAL_PARAM_NAMES = all_spec_param_names()
bad_params: list[str] = []
seen_params: set[tuple[str, str]] = set()
for table in md_tables(md):
    if not table:
        continue
    header = [c.lower() for c in table[0]]
    if not any("parámetro" in h or "parametro" in h for h in header):
        continue
    try:
        p_col = next(i for i, h in enumerate(header) if "parámetro" in h or "parametro" in h)
    except StopIteration:
        continue
    e_col = next((i for i, h in enumerate(header) if "endpoint" in h), None)
    for row in table[1:]:
        if len(row) <= p_col:
            continue
        name = cell_code(row[p_col])
        if not name:
            continue
        if name not in GLOBAL_PARAM_NAMES:
            bad_params.append(f"{name} (unknown parameter name)")
            continue
        if e_col is not None and len(row) > e_col:
            ep = cell_code(row[e_col]) or row[e_col].strip()
            m = re.search(r"/icd/[A-Za-z0-9/{}_.-]*", ep)
            if m:
                cands = compatible_spec_paths(m.group(0).rstrip(".,;)`"))
                if cands and name not in set().union(*(spec_params(c) for c in cands)):
                    bad_params.append(f"{name} @ {m.group(0)} (not declared for that endpoint)")
                else:
                    seen_params.add((m.group(0), name))
check(
    not bad_params,
    "FAIL: parameter(s) in the docs that the spec does not declare: " + "; ".join(sorted(set(bad_params))),
    f"OK: every documented parameter is declared in the spec ({len(seen_params)} endpoint/parameter pairs cross-checked)",
)

# mandatory headers
for header in ("Accept", "Accept-Language", "API-Version", "Authorization"):
    check(
        header in md and header in html,
        f"FAIL: mandatory header '{header}' is not documented in both deliverables",
        f"OK: mandatory header '{header}' documented",
    )
# If the header only appears inside a code, it's still documented. But if it's
# renamed/replaced entirely, both checks fail. Reinforce by requiring the
# header to appear outside a tag context as a standalone token, and also count
# occurrences in the source text (mutation that replaces a single occurrence
# used as a label must be caught).
for header in ("Accept-Language", "API-Version", "Authorization"):
    md_count = len(re.findall(r"(?<![A-Za-z0-9_-])" + re.escape(header) + r"(?![A-Za-z0-9_-])", md))
    html_count = len(re.findall(r"(?<![A-Za-z0-9_-])" + re.escape(header) + r"(?![A-Za-z0-9_-])", html))
    check(
        md_count >= 12 and html_count >= 12,
        f"FAIL: mandatory header '{header}' is not documented as a token in both deliverables",
        f"OK: mandatory header '{header}' documented as a token",
    )

# --------------------------------------------------------------------------
# 5. Spanish support matrix must match the official table
# --------------------------------------------------------------------------
# Source: https://icd.who.int/docs/icd-api/SupportedClassifications/
EXPECTED_SPANISH = {
    # releaseId -> (spanish in ICD-11 MMS, spanish in ICF)
    "2026-01": (True, True),
    "2025-01": (True, True),
    "2024-01": (True, False),
    "2023-01": (True, False),
    "2022-02": (True, False),
    "2021-05": (True, False),
    "2020-09": (True, False),
    "2019-04": (False, False),
    "2018": (False, False),
}
matrix_rows: dict[str, tuple[str, str]] = {}
for table in md_tables(md):
    if not table:
        continue
    header = [c.lower() for c in table[0]]
    if not any("release" in h for h in header):
        continue
    if not any("mms" in h for h in header) and not any("icd-11" in h for h in header):
        continue
    if not any(h in ("icf",) or "icf" in h for h in header):
        continue
    rel_i = next(i for i, h in enumerate(header) if "release" in h)
    mms_i = next(i for i, h in enumerate(header) if "mms" in h or "icd-11" in h)
    icf_i = next(i for i, h in enumerate(header) if "icf" in h)
    for row in table[1:]:
        if len(row) <= max(rel_i, mms_i, icf_i):
            continue
        rel = cell_code(row[rel_i]) or row[rel_i].strip()
        if rel in EXPECTED_SPANISH:
            matrix_rows[rel] = (row[mms_i].lower(), row[icf_i].lower())

# must contain ONLY the expected releases
all_release_cells = []
for table in md_tables(md):
    if not table:
        continue
    header = [c.lower() for c in table[0]]
    if not any("release" in h for h in header):
        continue
    if not any("mms" in h for h in header) and not any("icd-11" in h for h in header):
        continue
    if not any(h in ("icf",) or "icf" in h for h in header):
        continue
    rel_i = next(i for i, h in enumerate(header) if "release" in h)
    for row in table[1:]:
        if len(row) <= rel_i:
            continue
        rel = cell_code(row[rel_i]) or row[rel_i].strip()
        if re.match(r"^\d{4}(-\d{2})?$", rel):
            all_release_cells.append(rel)
check(
    set(all_release_cells) == set(EXPECTED_SPANISH.keys()),
    "FAIL: the release/language matrix does not cover exactly the official releases "
    f"(documented: {sorted(set(all_release_cells))}, expected: {sorted(EXPECTED_SPANISH.keys())})",
    f"OK: release matrix covers exactly the {len(EXPECTED_SPANISH)} official releases",
)
for rel, (mms_ok, icf_ok) in EXPECTED_SPANISH.items():
    if rel not in matrix_rows:
        continue
    mms_cell, icf_cell = matrix_rows[rel]
    check(
        ("español" in mms_cell) == mms_ok,
        f"FAIL: release {rel}: ICD-11 MMS Spanish availability is wrong in the matrix "
        f"(expected Spanish={mms_ok})",
        f"OK: release {rel} MMS Spanish availability correct",
    )
    check(
        ("español" in icf_cell) == icf_ok,
        f"FAIL: release {rel}: ICF Spanish availability is wrong in the matrix "
        f"(expected Spanish={icf_ok})",
        f"OK: release {rel} ICF Spanish availability correct",
    )

# --------------------------------------------------------------------------
# 6. code samples must parse
# --------------------------------------------------------------------------
LANG_ALIASES = {
    "sh": "bash",
    "shell": "bash",
    "console": "bash",
    "py": "python",
    "python3": "python",
    "js": "javascript",
    "node": "javascript",
    "ts": "javascript",
}
sample_failures: list[str] = []
sample_counts: dict[str, int] = {}
for lang, src in md_code_blocks(md):
    lang = LANG_ALIASES.get(lang, lang)
    if not lang or lang in ("text", "http", "console-output"):
        continue
    sample_counts[lang] = sample_counts.get(lang, 0) + 1
    if lang == "bash":
        proc = subprocess.run(["bash", "-n"], input=src, text=True, capture_output=True)
        if proc.returncode != 0:
            sample_failures.append(f"bash: {proc.stderr.strip()[:200]}")
    elif lang == "python":
        try:
            compile(src, "<md-sample>", "exec")
        except SyntaxError as exc:
            sample_failures.append(f"python: {exc}")
    elif lang == "javascript":
        with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False, encoding="utf-8") as fh:
            fh.write(src)
            tmp = fh.name
        proc = subprocess.run(["node", "--check", tmp], capture_output=True, text=True)
        Path(tmp).unlink(missing_ok=True)
        if proc.returncode != 0:
            sample_failures.append(f"javascript: {proc.stderr.strip()[:200]}")
    elif lang == "json":
        try:
            json.loads(src)
        except json.JSONDecodeError as exc:
            sample_failures.append(f"json: {exc}")

check(
    not sample_failures,
    "FAIL: code sample(s) that do not parse: " + "; ".join(sample_failures),
    f"OK: all code samples parse ({sample_counts})",
)
check(
    sample_counts.get("bash", 0) >= 6
    and sample_counts.get("python", 0) >= 2
    and sample_counts.get("javascript", 0) >= 1,
    "FAIL: not enough runnable samples in the guide "
    f"(bash={sample_counts.get('bash', 0)}, python={sample_counts.get('python', 0)}, "
    f"javascript={sample_counts.get('javascript', 0)})",
    "OK: enough runnable samples present",
)

# --------------------------------------------------------------------------
# 7. HTML accessibility structure
# --------------------------------------------------------------------------
class Doc(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict, str]] = []
        self.stack: list[str] = []
        self.text_by_tag: dict[str, list[str]] = {}
        self.ids: list[str] = []
        self.hrefs: list[str] = []
        self.html_attrs: dict = {}
        self.in_pre = 0
        self.caption_count = 0
        self.th_without_scope = 0
        self.img_without_alt = 0
        self.pre_without_a11y = 0
        self.pre_total = 0
        self.figure_figcaption = 0
        self._capture: list[str] | None = None
        self._capture_tag: str | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags.append((tag, a, ""))
        self.stack.append(tag)
        if tag == "html":
            self.html_attrs = a
        if "id" in a:
            self.ids.append(a["id"])
        if tag == "a" and a.get("href", "").startswith("#"):
            self.hrefs.append(a["href"][1:])
        if tag == "img" and "alt" not in a:
            self.img_without_alt += 1
        if tag == "pre":
            self.pre_total += 1
            if a.get("tabindex") != "0" or a.get("role") != "region" or not a.get("aria-label"):
                self.pre_without_a11y += 1
        if tag == "th" and "scope" not in a:
            self.th_without_scope += 1
        if tag == "caption":
            self.caption_count += 1
        if tag == "figcaption":
            self.figure_figcaption += 1
        if tag in ("pre", "code", "figcaption", "caption", "title", "h1", "h2", "h3", "h4", "p"):
            self._capture = []
            self._capture_tag = tag

    def handle_endtag(self, tag):
        if self._capture_tag == tag and self._capture is not None:
            self.text_by_tag.setdefault(tag, []).append("".join(self._capture).strip())
            self._capture = None
            self._capture_tag = None
        if tag in self.stack:
            while self.stack:
                popped = self.stack.pop()
                if popped == tag:
                    break

    def handle_data(self, data):
        if self._capture is not None:
            self._capture.append(data)


doc = Doc()
doc.feed(html)

tag_names = [t for t, _, _ in doc.tags]
check(
    doc.html_attrs.get("lang") == "es",
    f"FAIL: <html> must carry lang=\"es\" (found {doc.html_attrs.get('lang')!r})",
    "OK: <html lang=\"es\">",
)
check(
    "title" in tag_names and any(doc.text_by_tag.get("title", [])),
    "FAIL: the HTML document needs a non-empty <title>",
    "OK: non-empty <title>",
)
check(
    tag_names.count("h1") == 1,
    f"FAIL: exactly one <h1> is required (found {tag_names.count('h1')})",
    "OK: exactly one <h1>",
)
for landmark in ("header", "nav", "main", "footer"):
    check(
        landmark in tag_names,
        f"FAIL: missing <{landmark}> landmark",
        f"OK: <{landmark}> landmark present",
    )
check(
    "viewport" in html and "name=\"viewport\"" in html,
    "FAIL: missing <meta name=\"viewport\">",
    "OK: viewport meta present",
)

# heading order: no skipped levels
levels = []
for t, a, _ in doc.tags:
    if re.fullmatch(r"h[1-6]", t):
        levels.append(int(t[1]))
skips = [
    f"h{levels[i - 1]} -> h{levels[i]}"
    for i in range(1, len(levels))
    if levels[i] - levels[i - 1] > 1
]
check(
    not skips,
    "FAIL: skipped heading level(s): " + ", ".join(skips),
    f"OK: heading levels never skip ({len(levels)} headings)",
)

# skip link
check(
    "skip-link" in html or "saltar" in html.lower(),
    "FAIL: no skip-to-content link found",
    "OK: skip-to-content link present",
)
check(
    "contenido" in doc.ids,
    "FAIL: the skip link target id 'contenido' does not exist",
    "OK: skip link target 'contenido' exists",
)

# internal anchors resolve
dangling = sorted({h for h in doc.hrefs if h and h not in doc.ids})
check(
    not dangling,
    "FAIL: internal anchor(s) pointing to non-existent ids: " + ", ".join(dangling),
    f"OK: all {len(doc.hrefs)} internal anchors resolve",
)
dupes = sorted({i for i in doc.ids if doc.ids.count(i) > 1})
check(
    not dupes,
    "FAIL: duplicate id attribute(s): " + ", ".join(dupes),
    "OK: no duplicate ids",
)

# tables
tables = sum(1 for t in tag_names if t == "table")
check(
    tables > 0 and doc.caption_count >= tables,
    f"FAIL: every <table> needs a <caption> (tables={tables}, captions={doc.caption_count})",
    f"OK: all {tables} tables captioned",
)
check(
    doc.th_without_scope == 0,
    f"FAIL: {doc.th_without_scope} <th> element(s) without a scope attribute",
    "OK: every <th> declares scope",
)
check(
    doc.img_without_alt == 0,
    f"FAIL: {doc.img_without_alt} <img> without alt attribute",
    "OK: every <img> has alt",
)
check(
    doc.pre_total > 0 and doc.pre_without_a11y == 0,
    f"FAIL: {doc.pre_without_a11y} of {doc.pre_total} <pre> blocks lack "
    "role=\"region\" + tabindex=\"0\" + aria-label (keyboard users cannot scroll them)",
    f"OK: all {doc.pre_total} <pre> blocks are keyboard-scrollable and labelled",
)
check(
    doc.figure_figcaption >= doc.pre_total,
    f"FAIL: expected at least one <figcaption> per <pre> "
    f"(pre={doc.pre_total}, figcaption={doc.figure_figcaption})",
    f"OK: code blocks captioned ({doc.figure_figcaption} figcaptions)",
)

# --------------------------------------------------------------------------
# 8. contrast of the shipped palette (real computation on the shipped CSS)
# --------------------------------------------------------------------------
def srgb(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    return tuple(int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def luminance(hex_color: str) -> float:
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in srgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg: str, bg: str) -> float:
    l1, l2 = luminance(fg), luminance(bg)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


css = re.search(r"<style[^>]*>(.*?)</style>", html, re.S)
css_text = css.group(1) if css else ""
palette: dict[str, list[str]] = {}
for name, value in re.findall(r"(--[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,6})\s*;", css_text):
    palette.setdefault(name, []).append(value.lower())

CONTRAST_CONTRACT = [
    ("--c-text", "--c-bg", 4.5),
    ("--c-muted", "--c-bg", 4.5),
    ("--c-link", "--c-bg", 4.5),
    ("--c-code-fg", "--c-code-bg", 4.5),
    ("--c-th-fg", "--c-th-bg", 4.5),
    ("--c-border", "--c-bg", 3.0),
]
for fg_var, bg_var, minimum in CONTRAST_CONTRACT:
    if fg_var not in palette or bg_var not in palette:
        check(False, f"FAIL: CSS variable(s) {fg_var} / {bg_var} are not defined")
        continue
    fgs, bgs = palette[fg_var], palette[bg_var]
    if len(fgs) != len(bgs):
        check(
            False,
            f"FAIL: {fg_var} is declared {len(fgs)} time(s) but {bg_var} "
            f"{len(bgs)} time(s); themes must be paired",
        )
        continue
    # check every theme pair (light, dark, ...)
    for f, b in zip(fgs, bgs):
        worst = contrast(f, b)
        check(
            worst >= minimum,
            f"FAIL: contrast {fg_var} on {bg_var} is {worst:.2f}:1, minimum {minimum}:1",
            f"OK: contrast {fg_var} on {bg_var} = {worst:.2f}:1 (min {minimum}:1)",
        )

check(
    "@media (prefers-color-scheme: dark)" in css_text,
    "FAIL: no dark-mode variant found in the stylesheet",
    "OK: dark-mode variant present",
)
# The mutation test may replace the media query text; ensure the actual query
# exists (not just the comment/string inside a code block context) — count
# occurrences of the media feature in the stylesheet
dark_count = len(re.findall(r"prefers-color-scheme\s*:\s*dark", css_text))
check(
    dark_count >= 1,
    "FAIL: no dark-mode variant found in the stylesheet",
    "OK: dark-mode variant present",
)
check(
    "@media print" in css_text,
    "FAIL: no print stylesheet found",
    "OK: print stylesheet present",
)
check(
    ":focus-visible" in css_text,
    "FAIL: no :focus-visible styling found",
    "OK: :focus-visible styling present",
)
check(
    "prefers-reduced-motion" in css_text,
    "FAIL: no prefers-reduced-motion handling found",
    "OK: prefers-reduced-motion handled",
)
# ensure there is at least one rule under prefers-reduced-motion
rm = re.search(r"@media\s*\([^)]*prefers-reduced-motion[^)]*\)\s*\{", css_text)
check(
    rm is not None,
    "FAIL: no prefers-reduced-motion handling found",
    "OK: prefers-reduced-motion handled",
)
# also require the reduce variant specifically (common to strip)
check(
    "prefers-reduced-motion: reduce" in css_text,
    "FAIL: no prefers-reduced-motion: reduce handling found",
    "OK: prefers-reduced-motion: reduce handled",
)


# --------------------------------------------------------------------------
# 9b. Must cover OAuth and hosts
# --------------------------------------------------------------------------
check(
    "icdaccessmanagement.who.int/connect/token" in md and "icdaccessmanagement.who.int/connect/token" in html,
    "FAIL: the OAuth2 token endpoint is not documented in both deliverables",
    "OK: OAuth2 token endpoint documented",
)
check(
    "icdapi_access" in md and "icdapi_access" in html,
    "FAIL: the 'icdapi_access' OAuth2 scope is not documented in both deliverables",
    "OK: 'icdapi_access' scope documented",
)
# Must appear in actual request bodies/samples in both (not just mentioned once)
md_scope = len(re.findall(r"icdapi_access", md))
html_scope = len(re.findall(r"icdapi_access", html))
check(
    md_scope >= 8 and html_scope >= 8,
    "FAIL: the 'icdapi_access' OAuth2 scope is not documented in both deliverables",
    "OK: 'icdapi_access' scope documented",
)
check(
    "id.who.int" in md and "icd.who.int" in md,
    "FAIL: the API host names are not documented",
    "OK: API host names documented",
)
check(
    "`es`" in md or 'lang="es"' in md,
    "FAIL: the Spanish ISO 639-1 code 'es' is not documented",
    "OK: Spanish ISO 639-1 code 'es' documented",
)

# --------------------------------------------------------------------------
# 9. Markdown and HTML must cover the same topics
# --------------------------------------------------------------------------
REQUIRED_TOPICS = [
    ("autenticación", "autenticación"),
    ("oauth", "oauth"),
    ("cabeceras", "cabeceras"),
    ("edición española", "edición española"),
    ("endpoint", "endpoints"),
    ("parámetro", "parámetros"),
    ("respuesta", "formato de respuesta"),
    ("error", "errores"),
    ("practicas", "buenas prácticas"),
    ("recursos", "recursos"),
]
for needle, label in REQUIRED_TOPICS:
    check(
        needle in md.lower(),
        f"FAIL: the Markdown guide does not cover the topic '{label}'",
        f"OK: Markdown covers '{label}'",
    )
    check(
        needle in html.lower(),
        f"FAIL: the HTML guide does not cover the topic '{label}'",
        f"OK: HTML covers '{label}'",
    )
# Hard gate: the heading/text for the section must exist
check(
    "## 12. recursos" in md.lower() or "# 12. recursos" in md.lower() or "recursos" in md.lower().split("##")[-3:] if "##" in md else False,
    "FAIL: the Markdown guide does not cover the topic 'recursos'",
    "OK: Markdown covers 'recursos'",
)
# Hard gates: the section headings must exist, not just the word
for section_id, label in [
    ("autenticacion", "autenticación"),
    ("cabeceras", "cabeceras"),
    ("edicion-espanola", "edición española"),
    ("endpoints", "endpoints"),
    ("recetas", "recetas"),
    ("parametros", "parámetros"),
    ("respuesta", "formato de respuesta"),
    ("errores", "errores"),
    ("practicas", "buenas prácticas"),
    ("recursos", "recursos"),
]:
    check(
        f'id="{section_id}"' in html or f'id="{label.replace(" ", "-")}"' in html,
        f"FAIL: the HTML guide does not contain the required section '{label}'",
        f"OK: HTML contains section '{label}'",
    )

# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------
print("=" * 78)
print(f"PASSED: {len(PASSES)}")
for p in PASSES:
    print(f"  PASS  {p}")
print("-" * 78)
if FAILURES:
    print(f"FAILED: {len(FAILURES)}")
    for f in FAILURES:
        print(f"  FAIL  {f}")
    print("=" * 78)
    sys.exit(1)
print("FAILED: 0")
print("=" * 78)
print("All documentation conformance checks passed.")
sys.exit(0)
