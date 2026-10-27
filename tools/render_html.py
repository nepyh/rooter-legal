#!/usr/bin/env python3
"""Render src/<slug>/<version>.md into <slug>/<version>/index.html plus a root index.

Usage:
  python3 tools/render_html.py            # write files
  python3 tools/render_html.py --check    # render in memory, fail if committed files differ
  python3 tools/render_html.py --site DIR # write files, then assemble the Pages artifact in DIR

No third-party dependencies: the supported subset is headings, ordered/unordered lists,
blockquotes, fenced code, rules, pipe tables, paragraphs and **bold** / `code` inline spans.
"""

import html
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
MONTHS = ("January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December")

SERVICE = "루터(rooter)"

CSS = """
:root { color-scheme: light }
* { box-sizing: border-box }
body {
  margin: 0;
  padding: 2.5rem 1.25rem 5rem;
  background: #fbfbfc;
  color: #1c1d21;
  font-family: "Apple SD Gothic Neo", "Pretendard", "Noto Sans KR", system-ui, -apple-system, "Segoe UI", sans-serif;
  font-size: 16px;
  line-height: 1.75;
  -webkit-text-size-adjust: 100%;
  word-break: keep-all;
  overflow-wrap: anywhere;
}
main { max-width: 46rem; margin: 0 auto }
header { padding-bottom: 1.5rem; border-bottom: 1px solid #e4e5ea }
header .service { margin: 0 0 .35rem; font-size: .8rem; letter-spacing: .08em; text-transform: uppercase; color: #6b6f7a }
h1 { margin: 0; font-size: 1.6rem; line-height: 1.4; letter-spacing: -.01em }
header .meta { margin: .65rem 0 0; font-size: .9rem; color: #6b6f7a }
h2 { margin: 2.75rem 0 1rem; padding-top: 1.5rem; border-top: 1px solid #e4e5ea; font-size: 1.15rem; letter-spacing: -.01em }
h3 { margin: 2rem 0 .6rem; font-size: 1rem }
p { margin: .85rem 0 }
ol, ul { margin: .85rem 0; padding-left: 1.5rem }
li { margin: .4rem 0 }
li > p { margin: .4rem 0 }
blockquote { margin: 1.25rem 0; padding: .75rem 1rem; border-left: 3px solid #d4d6dd; background: #fff; color: #3d4049 }
pre { margin: 1.25rem 0; padding: 1rem; overflow-x: auto; background: #f1f2f5; border-radius: 6px; font-size: .875rem; line-height: 1.6 }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .9em }
hr { margin: 2rem 0; border: 0; border-top: 1px solid #e4e5ea }
a { color: #2450a4; text-underline-offset: .15em }
footer { max-width: 46rem; margin: 3rem auto 0; padding-top: 1.25rem; border-top: 1px solid #e4e5ea; font-size: .875rem; color: #6b6f7a }
.table-wrap { margin: 1.25rem 0; overflow-x: auto }
table { width: 100%; border-collapse: collapse; font-size: .9rem; line-height: 1.6 }
th, td { padding: .55rem .7rem; border: 1px solid #e4e5ea; text-align: left; vertical-align: top }
th { background: #f1f2f5; font-weight: 600; white-space: nowrap }
td { background: #fff }
.index li { margin: .6rem 0 }
.index .stamp { color: #6b6f7a; font-size: .875rem }
@media print {
  body { padding: 0; background: #fff; font-size: 11pt }
  header { border-bottom: 0 }
  h2 { page-break-after: avoid }
  h3 { page-break-after: avoid }
  a { color: inherit; text-decoration: none }
}
"""


def page(title, description, body, footer="", source=None):
    note = ""
    if source:
        note = (
            "<!-- This file is rendered from %s in nepyh/rooter-legal. "
            "Edit that source file instead of this one. -->\n" % source
        )
    return (
        "<!doctype html>\n"
        '<html lang="ko">\n'
        "<head>\n"
        "%s"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>%s</title>\n"
        '<meta name="description" content="%s">\n'
        "<style>%s</style>\n"
        "</head>\n"
        "<body>\n"
        "<main>\n%s\n</main>\n%s\n</body>\n</html>\n"
    ) % (note, html.escape(title), html.escape(description), CSS, body, footer)


def parse_front_matter(text):
    if not text.startswith("---\n"):
        raise SystemExit("front matter missing (file must start with ---)")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise SystemExit("front matter not terminated")
    meta = {}
    for line in text[4:end].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise SystemExit("bad front matter line: %r" % line)
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip()
    return meta, text[end + 5:]


def inline(text):
    out = html.escape(text, quote=False)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"`(.+?)`", r"<code>\1</code>", out)
    return out


BLOCK_START = re.compile(r"^(#{1,6}\s|```|>\s?|\s*(?:\d+\.|-)\s|---\s*$|\|)")
TABLE_SEPARATOR = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
LIST_LINE = re.compile(r"^( *)(?:(\d+)\.|-)\s+(.*)$")


def parse_list_block(lines, start):
    """Collect consecutive list lines (any indent) plus their continuation lines."""
    entries = []
    i = start
    while i < len(lines):
        match = LIST_LINE.match(lines[i])
        if match:
            entries.append([len(match.group(1)), match.group(2) is not None, match.group(3)])
            i += 1
        elif entries and lines[i].strip() and lines[i].startswith(" ") and not BLOCK_START.match(lines[i]):
            entries[-1][2] += " " + lines[i].strip()
            i += 1
        else:
            break
    return entries, i


def render_list(entries):
    """Render entries as nested <ul>/<ol> by indentation, nesting sub-lists inside the parent <li>."""

    def build(pos, base):
        tag = "ol" if entries[pos][1] else "ul"
        out = ["<%s>" % tag]
        li_open = False
        while pos < len(entries) and entries[pos][0] >= base:
            indent, _ordered, text = entries[pos]
            if indent > base:
                sub, pos = build(pos, indent)
                if not li_open:
                    out.append("<li>")
                    li_open = True
                out.append(sub)
                continue
            if li_open:
                out.append("</li>")
            out.append("<li>" + inline(text))
            li_open = True
            pos += 1
        if li_open:
            out.append("</li>")
        out.append("</%s>" % tag)
        return "".join(out), pos

    rendered, _ = build(0, entries[0][0])
    return rendered


def table_cells(line):
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def render_table(lines, start):
    """Pipe table: header row, separator row (---), then body rows. Returns (html, next index)."""
    header = table_cells(lines[start])
    i = start + 2
    rows = []
    while i < len(lines) and lines[i].startswith("|"):
        rows.append(table_cells(lines[i]))
        i += 1
    head = "".join("<th>%s</th>" % inline(cell) for cell in header)
    body = "\n".join(
        "<tr>%s</tr>" % "".join("<td>%s</td>" % inline(cell) for cell in row) for row in rows
    )
    return (
        '<div class="table-wrap"><table>\n<thead><tr>%s</tr></thead>\n<tbody>\n%s\n</tbody>\n</table></div>'
        % (head, body),
        i,
    )


def render_body(markdown_text):
    lines = markdown_text.splitlines()
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue

        if line.startswith("```"):
            i += 1
            buf = []
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(html.escape(lines[i], quote=False))
                i += 1
            i += 1
            out.append("<pre><code>%s</code></pre>" % "\n".join(buf))
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            out.append("<h%d>%s</h%d>" % (level, inline(m.group(2)), level))
            i += 1
            continue

        if re.match(r"^---\s*$", line):
            out.append("<hr>")
            i += 1
            continue

        if line.startswith("|") and i + 1 < len(lines) and TABLE_SEPARATOR.match(lines[i + 1]):
            table, i = render_table(lines, i)
            out.append(table)
            continue

        if LIST_LINE.match(line):
            entries, i = parse_list_block(lines, i)
            out.append(render_list(entries))
            continue

        if re.match(r"^>\s?", line):
            buf = []
            while i < len(lines) and re.match(r"^>\s?", lines[i]):
                buf.append(re.sub(r"^>\s?", "", lines[i]))
                i += 1
            out.append("<blockquote><p>%s</p></blockquote>" % inline(" ".join(buf)))
            continue

        buf = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not BLOCK_START.match(lines[i]):
            buf.append(lines[i])
            i += 1
        out.append("<p>%s</p>" % inline(" ".join(buf)))

    return "\n".join(out)


def human_date(iso):
    year, month, day = iso.split("-")
    return "%s년 %d월 %d일" % (year, int(month), int(day))


def load_documents():
    docs = []
    for path in sorted(SRC.glob("*/*.md")):
        slug, version = path.parent.name, path.stem
        meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
        for key in ("code", "version", "title", "effective_date"):
            if not meta.get(key):
                raise SystemExit("%s: front matter missing %r" % (path, key))
        if meta["code"] != slug.upper():
            raise SystemExit("%s: code %r does not match directory %r" % (path, meta["code"], slug))
        if meta["version"] != version:
            raise SystemExit("%s: version %r does not match filename %r" % (path, meta["version"], version))
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", meta["effective_date"]):
            raise SystemExit("%s: effective_date must be YYYY-MM-DD" % path)
        docs.append({
            "slug": slug,
            "version": version,
            "meta": meta,
            "body": body,
            "source": path,
            "url": "%s/%s/" % (slug, version),
        })
    if not docs:
        raise SystemExit("no documents found under src/")
    return docs


def render_document(doc):
    meta = doc["meta"]
    body = strip_comments(doc["body"])
    header = (
        "<header>\n"
        '<p class="service">%s</p>\n'
        "<h1>%s</h1>\n"
        '<p class="meta">버전 %s · %s 시행</p>\n'
        "</header>"
    ) % (SERVICE, html.escape(meta["title"]), html.escape(meta["version"]), human_date(meta["effective_date"]))
    content = "%s\n%s" % (header, render_body(body))
    footer = (
        '<footer>\n'
        "<p>%s · %s · 버전 %s</p>\n"
        "</footer>"
    ) % (html.escape(meta["title"]), human_date(meta["effective_date"]), html.escape(meta["version"]))
    return page(
        "%s · %s" % (meta["title"], SERVICE),
        "%s (버전 %s, %s 시행)" % (meta["title"], meta["version"], human_date(meta["effective_date"])),
        content,
        footer,
        source="src/%s/%s.md" % (doc["slug"], doc["version"]),
    )


def render_index(docs):
    latest = {}
    for doc in docs:
        key = doc["slug"]
        if key not in latest or doc["version"] > latest[key]["version"]:
            latest[key] = doc
    items = []
    for doc in sorted(latest.values(), key=lambda d: d["meta"]["title"]):
        items.append(
            '<li><a href="%s">%s</a> <span class="stamp">— 버전 %s · %s 시행</span></li>'
            % (doc["url"], html.escape(doc["meta"]["title"]), html.escape(doc["version"]),
               human_date(doc["meta"]["effective_date"]))
        )
    body = (
        "<header>\n"
        '<p class="service">%s</p>\n'
        "<h1>약관 및 정책</h1>\n"
        "</header>\n"
        '<ul class="index">\n%s\n</ul>'
    ) % (SERVICE, "\n".join(items))
    return page(
        "%s 약관 및 정책" % SERVICE,
        "루터(rooter) 서비스 약관 및 정책",
        body,
        source="src/<slug>/<version>.md (every document under src/)",
    )


def strip_comments(text):
    return re.sub(r"<!--.*?-->\s*", "", text, flags=re.S)


def outputs(docs):
    files = {pathlib.Path("index.html"): render_index(docs)}
    for doc in docs:
        files[pathlib.Path(doc["slug"]) / doc["version"] / "index.html"] = render_document(doc)
    return files


def main(argv):
    mode = argv[1] if len(argv) > 1 else ""
    site_dir = argv[2] if len(argv) > 2 and argv[1] == "--site" else None
    files = outputs(load_documents())

    if mode == "--check":
        stale = [str(rel) for rel, text in files.items()
                 if not (ROOT / rel).exists() or (ROOT / rel).read_text(encoding="utf-8") != text]
        if stale:
            print("generated files are out of date, run: python3 tools/render_html.py")
            for rel in stale:
                print("  " + rel)
            return 1
        print("ok: %d generated files up to date" % len(files))
        return 0

    for rel, text in files.items():
        target = ROOT / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        print("wrote " + str(rel))

    if site_dir:
        site = ROOT / site_dir
        if site.exists():
            shutil.rmtree(site)
        for rel in files:
            dest = site / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, dest)
        print("assembled " + str(site))
    return 0


sys.exit(main(sys.argv))
