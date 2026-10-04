#!/usr/bin/env python3
"""Markdown 보고서를 번뜩번뜩 작은별 표지가 붙은 HTML(선택: PDF)로 만든다.

사용법
  python3 make_report_html.py 보고서.md                      → 보고서.html + 보고서_assets/
  python3 make_report_html.py 보고서.md -o out/report.html
  python3 make_report_html.py 보고서.md --single-file        → 표지 이미지까지 HTML 한 파일에 포함
  python3 make_report_html.py 보고서.md --pdf                → Chrome으로 PDF도 생성

표지
  기본으로 스크립트 옆의 표지.png를 A4 전면 배경으로 쓴다(--cover로 변경, .png·.jpg·.docx 가능).
  .docx를 지정하면 그 안의 배경 이미지를 꺼내 쓴다.
  글꼴은 Pretendard다. 설치돼 있으면 그것을, 없으면 jsDelivr CDN의 웹폰트를 쓴다.
  표지 배경을 바꾸면 CSS의 --split(배경 경계)·--logo-left·--logo-width(BBLS 로고 위치)를 새 이미지에 맞춰 고친다.
  표지 문구는 Markdown 맨 앞의 front matter로 정한다. 없으면 첫 번째 '# 제목'을 제목으로 쓰고,
  제목 바로 아래 '·'가 들어간 한 줄 문단(예: "1차 발표용 · 번뜩번뜩 작은별 · 작성 기준일 …")은 본문에서 빼고,
  그중 '작성 기준일 YYYY-MM-DD'의 날짜만 표지 하단에 쓴다(front matter의 date가 있으면 그 값을 쓴다).

  ---
  title: LLM 서빙 엔진 업데이트 보안 검증 조사보고서
  subtitle: 1차 발표용 조사보고서
  team: 번뜩번뜩 작은별
  date: 2026-10-04
  version: 검토용 초안 v0.3
  cover_label: 프로젝트 사전조사 보고서   (선택: 큰 제목 위의 작은 문구)
  cover_title: LLM 서빙 엔진 | 업데이트 보안 검증 | 조사보고서   (선택: 큰 제목 줄바꿈 지정)
  ---

지원하는 Markdown
  제목(#~######), 문단, **굵게**, *기울임*, `코드`, [링크](url), 자동 링크, 목록(중첩·번호),
  표(정렬 포함), 인용(> 안의 목록·표 포함), 코드 블록, ```mermaid 도식, 가로줄.
  참고문헌 목록의 "- [R01] …"·"- [T1] …" 항목에는 앵커를 달고, 본문의 [R01]·[R08~R11]·[T12]를 그 항목에 연결한다.

표준 라이브러리만 사용한다(Python 3.9+). PDF 생성에는 Google Chrome이 필요하다.
"""

import argparse
import base64
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_COVER = SCRIPT_DIR / "표지.png"
DEFAULT_LABEL = ""  # 큰 제목 위 작은 문구. 기본은 쓰지 않는다(front matter의 cover_label로 지정 가능)
DEFAULT_TEAM = "번뜩번뜩작은별"
CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome", "chromium", "chromium-browser",
]

LIST_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
FENCE_RE = re.compile(r"^\s*(```+|~~~+)\s*([\w+-]*)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
HR_RE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
CITE_RE = re.compile(r"\[((?:R|T)\d{1,2})((?:~(?:R|T)?\d{1,2})?)\]")
REF_ITEM_RE = re.compile(r"^\s*[-*+]\s+\[((?:R|T)\d{1,2})\]")


# ---------------------------------------------------------------- front matter

def split_front_matter(text):
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    meta = {}
    for line in text[4:end].splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip().strip("\"'")
    return meta, text[end + 4:].lstrip("\n")


# ---------------------------------------------------------------- inline

class Context:
    def __init__(self, ref_ids, toc_depth):
        self.ref_ids = ref_ids
        self.toc_depth = toc_depth
        self.toc = []
        self.count = 0
        self.mermaid = False

    def heading(self, level, raw):
        self.count += 1
        hid = f"s{self.count}"
        text = inline(raw, self)
        if 2 <= level <= self.toc_depth:
            self.toc.append((level, re.sub(r"<[^>]+>", "", text), hid))
        return f'<h{level} id="{hid}">{text}</h{level}>'


def inline(s, ctx):
    slots = []

    def keep(fragment):
        slots.append(fragment)
        return f"\x00{len(slots) - 1}\x00"

    # 코드 구간은 다른 변환에서 보호한다
    s = re.sub(r"(`+)(.+?)\1", lambda m: keep("<code>" + html.escape(m.group(2).strip()) + "</code>"), s)

    def link(m):
        return keep(f'<a href="{html.escape(m.group(2), quote=True)}">') + m.group(1) + keep("</a>")

    s = re.sub(r"\[([^\[\]]+)\]\(([^)\s]+)\)", link, s)
    s = html.escape(s, quote=False)
    s = re.sub(r"&lt;br\s*/?&gt;", "<br>", s)

    def autolink(m):
        url = m.group(1)
        tail = ""
        while url and url[-1] in ".,;:)":
            tail = url[-1] + tail
            url = url[:-1]
        return keep(f'<a href="{url}">{url}</a>') + tail

    s = re.sub(r"(https?://[^\s<\x00]+)", autolink, s)

    def cite(m):
        rid = m.group(1)
        if rid not in ctx.ref_ids:
            return m.group(0)
        return keep(f'<a class="cite" href="#ref-{rid}">[{rid}{m.group(2)}]</a>')

    s = CITE_RE.sub(cite, s)

    # "[R67, GitHub 권고 API 집계]"처럼 번호 뒤에 설명이 붙은 인용은 번호만 연결한다
    def cite_with_note(m):
        rid = m.group(1)
        if rid not in ctx.ref_ids:
            return m.group(0)
        return "[" + keep(f'<a class="cite" href="#ref-{rid}">{rid}</a>') + ","

    s = re.sub(r"\[((?:R|T)\d{1,2}),", cite_with_note, s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![*\w])\*(?![\s*])(.+?)(?<![\s*])\*(?![*\w])", r"<em>\1</em>", s)
    while "\x00" in s:
        s = re.sub(r"\x00(\d+)\x00", lambda m: slots[int(m.group(1))], s)
    return s


# ---------------------------------------------------------------- blocks

def indent_of(line):
    return len(line) - len(line.lstrip(" "))


def starts_block(line):
    stripped = line.lstrip()
    return (stripped.startswith(("#", ">", "|", "```", "~~~"))
            or bool(LIST_RE.match(line)) or bool(HR_RE.match(line)))


def split_row(row):
    row = row.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|") and not row.endswith("\\|"):
        row = row[:-1]
    # 코드 구간 안의 | 는 셀 구분으로 보지 않는다
    cells, buf, in_code = [], "", False
    for i, ch in enumerate(row):
        if ch == "`":
            in_code = not in_code
        if ch == "|" and not in_code and (i == 0 or row[i - 1] != "\\"):
            cells.append(buf)
            buf = ""
        else:
            buf += ch
    cells.append(buf)
    return [c.strip().replace("\\|", "|") for c in cells]


def render_table(rows, sep, ctx):
    aligns = []
    for cell in split_row(sep):
        if cell.startswith(":") and cell.endswith(":"):
            aligns.append("center")
        elif cell.endswith(":"):
            aligns.append("right")
        else:
            aligns.append("")

    def cell_html(tag, text, idx):
        align = aligns[idx] if idx < len(aligns) else ""
        attr = f' style="text-align:{align}"' if align else ""
        return f"<{tag}{attr}>{inline(text, ctx)}</{tag}>"

    head = split_row(rows[0])
    out = ['<div class="table-wrap"><table><thead><tr>']
    out += [cell_html("th", c, i) for i, c in enumerate(head)]
    out.append("</tr></thead><tbody>")
    for row in rows[1:]:
        cells = split_row(row)
        cells += [""] * (len(head) - len(cells))
        out.append("<tr>" + "".join(cell_html("td", c, i) for i, c in enumerate(cells[:len(head)])) + "</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def parse_list(lines, i, ctx):
    first = LIST_RE.match(lines[i])
    base = len(first.group(1))
    ordered = first.group(2)[0].isdigit()
    start = int(re.match(r"\d+", first.group(2)).group()) if ordered else 1
    items, loose, n = [], False, len(lines)

    while i < n:
        m = LIST_RE.match(lines[i])
        if not m or len(m.group(1)) != base or m.group(2)[0].isdigit() != ordered:
            break
        content_indent = len(m.group(1)) + len(m.group(2)) + 1
        body = [m.group(3)]
        i += 1
        while i < n:
            line = lines[i]
            if not line.strip():
                k = i + 1
                while k < n and not lines[k].strip():
                    k += 1
                if k < n and indent_of(lines[k]) > base:
                    body.append("")
                    i += 1
                    continue
                break
            if indent_of(line) > base:
                body.append(line[min(content_indent, indent_of(line)):])
                i += 1
                continue
            if not starts_block(line):
                body.append(line.strip())
                i += 1
                continue
            break
        items.append(body)
        k = i
        while k < n and not lines[k].strip():
            k += 1
        if k > i and k < n:
            m2 = LIST_RE.match(lines[k])
            if m2 and len(m2.group(1)) == base and m2.group(2)[0].isdigit() == ordered:
                loose = True
                i = k

    tag = "ol" if ordered else "ul"
    attr = f' start="{start}"' if ordered and start != 1 else ""
    out = [f"<{tag}{attr}>"]
    for body in items:
        inner = parse_blocks(body, ctx)
        if not loose and "" not in body:
            inner = re.sub(r"^<p>(.*?)</p>", r"\1", inner, count=1, flags=re.S)
        ref = re.match(r"^\[((?:R|T)\d{1,2})\]", body[0])
        li_attr = f' id="ref-{ref.group(1)}" class="ref"' if ref and ref.group(1) in ctx.ref_ids else ""
        out.append(f"<li{li_attr}>{inner}</li>")
    out.append(f"</{tag}>")
    return i, "".join(out)


def parse_blocks(lines, ctx):
    out, i, n = [], 0, len(lines)
    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue

        m = FENCE_RE.match(line)
        if m:
            fence, lang, buf = m.group(1), m.group(2), []
            i += 1
            while i < n and not lines[i].strip().startswith(fence):
                buf.append(lines[i])
                i += 1
            i += 1
            code = "\n".join(buf)
            if lang == "mermaid":
                ctx.mermaid = True
                out.append(f'<div class="mermaid">{html.escape(code)}</div>')
            else:
                out.append(f'<pre><code class="lang-{lang}">{html.escape(code)}</code></pre>')
            continue

        m = HEADING_RE.match(line)
        if m:
            out.append(ctx.heading(len(m.group(1)), m.group(2)))
            i += 1
            continue

        if HR_RE.match(line):
            out.append("<hr>")
            i += 1
            continue

        if line.lstrip().startswith("|") and i + 1 < n and TABLE_SEP_RE.match(lines[i + 1]):
            rows, sep = [line], lines[i + 1]
            i += 2
            while i < n and lines[i].lstrip().startswith("|"):
                rows.append(lines[i])
                i += 1
            out.append(render_table(rows, sep, ctx))
            continue

        if line.lstrip().startswith(">"):
            buf = []
            while i < n and lines[i].lstrip().startswith(">"):
                s = lines[i].lstrip()[1:]
                buf.append(s[1:] if s.startswith(" ") else s)
                i += 1
            out.append(f"<blockquote>{parse_blocks(buf, ctx)}</blockquote>")
            continue

        if LIST_RE.match(line):
            i, fragment = parse_list(lines, i, ctx)
            out.append(fragment)
            continue

        buf = [line.strip()]
        i += 1
        while i < n and lines[i].strip() and not starts_block(lines[i]):
            buf.append(lines[i].strip())
            i += 1
        out.append("<p>" + inline(" ".join(buf), ctx) + "</p>")
    return "\n".join(out)


# ---------------------------------------------------------------- cover assets

def extract_cover(cover, asset_dir, single_file):
    """표지 이미지(.png·.jpg) 또는 docx에서 배경 이미지를 준비한다. (이미지 src, 추가 CSS)를 돌려준다."""
    if cover.suffix.lower() == ".docx":
        with zipfile.ZipFile(cover) as z:
            media = [n for n in z.namelist() if n.startswith("word/media/")]
            if not media:
                sys.exit(f"표지 이미지가 없습니다: {cover}")
            image_name = max(media, key=lambda n: z.getinfo(n).file_size)
            image_bytes = z.read(image_name)
        image_ext = Path(image_name).suffix.lower()
    elif cover.suffix.lower() in (".png", ".jpg", ".jpeg"):
        image_bytes, image_ext = cover.read_bytes(), cover.suffix.lower()
        if image_ext == ".jpeg":
            image_ext = ".jpg"
    else:
        sys.exit(f"표지는 .png, .jpg, .docx 중 하나여야 합니다: {cover}")

    image_bytes, ext = compress_image(image_bytes, image_ext)
    mime = "image/jpeg" if ext == ".jpg" else "image/png"

    if single_file:
        src = f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"
    else:
        asset_dir.mkdir(parents=True, exist_ok=True)
        (asset_dir / f"cover{ext}").write_bytes(image_bytes)
        src = f"{asset_dir.name}/cover{ext}"
    return src, ""


def compress_image(data, ext):
    """macOS의 sips가 있으면 PNG 표지를 JPEG로 줄인다(약 7MB → 1MB 안팎)."""
    if ext != ".png" or not shutil.which("sips"):
        return data, ext
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp) / "in.png", Path(tmp) / "out.jpg"
        src.write_bytes(data)
        result = subprocess.run(
            ["sips", "-s", "format", "jpeg", "-s", "formatOptions", "88", str(src), "--out", str(dst)],
            capture_output=True)
        if result.returncode == 0 and dst.exists():
            return dst.read_bytes(), ".jpg"
    return data, ext


# ---------------------------------------------------------------- page

CSS = r"""
:root{
  --navy:#0B163F; --blue:#6688CC; --yellow:#FFD45C; --mist:#F7F8FC; --gray:#E5E7EB;
  --text:#1D2433; --muted:#5A6378;
  /* 표지.png 기준 위치(폭 대비 %): 크림·네이비 경계, BBLS 로고의 왼쪽 끝과 폭 */
  --split:36.209%; --logo-left:3.79%; --logo-width:28.53%;
  --font:'Pretendard Variable',Pretendard,-apple-system,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;
}
*{box-sizing:border-box}
html{-webkit-print-color-adjust:exact;print-color-adjust:exact}
body{margin:0;background:var(--gray);color:var(--text);
  font-family:var(--font);
  font-size:10.5pt;line-height:1.72;word-break:keep-all;overflow-wrap:break-word}

/* ---------- cover ---------- */
.cover{position:relative;width:min(210mm,100%);aspect-ratio:210/297;margin:24px auto;
  overflow:hidden;container-type:inline-size;background:#F3F0E9;box-shadow:0 2px 16px rgba(11,22,63,.18)}
.cover-bg{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
/* 팀 이름과 작성 기준일은 BBLS 로고 폭 안에서 가운데 정렬한다 */
.logo-fit{text-align:center;width:var(--logo-width)}
.cover-team{position:absolute;top:17.3cqw;left:var(--logo-left);margin:0;color:var(--navy);
  font-size:3.75cqw;font-weight:700;line-height:1;letter-spacing:-.01em}
/* 제목은 같은 내용을 두 겹으로 그리고, 배경 경계(--split)에서 잘라 색을 반전한다 */
.cover-title-wrap{position:absolute;left:0;right:0;bottom:20%;padding-left:var(--logo-left)}
.cover-title-wrap.on-light{color:var(--navy);clip-path:inset(0 calc(100% - var(--split)) 0 0)}
.cover-title-wrap.on-dark{color:var(--mist);clip-path:inset(0 0 0 var(--split))}
.cover-kicker{margin:0 0 2.2cqw;font-size:2.4cqw;font-weight:700;letter-spacing:.04em;color:var(--blue)}
.cover-title{margin:0;color:inherit;font-weight:900;line-height:1.16;letter-spacing:-.025em}
.cover-info{position:absolute;left:var(--logo-left);bottom:5.5%;width:var(--logo-width);color:var(--navy)}
.cover-info .logo-fit{width:100%}
.cover-meta{margin:0;font-size:2.15cqw;line-height:1.4;font-weight:700;color:var(--navy)}
.logo-fit{white-space:nowrap}

/* ---------- body sheet ---------- */
.sheet{width:min(210mm,100%);margin:24px auto 48px;background:#fff;padding:20mm 18mm;
  box-shadow:0 2px 16px rgba(11,22,63,.10)}
.toc{margin-bottom:12mm}
.toc h2{margin-top:0}
.toc ol{list-style:none;padding:0;margin:0}
.toc li a{display:block;color:var(--text);text-decoration:none;padding:3px 0;border-bottom:1px solid var(--gray)}
.toc li.l2 a{font-weight:700;color:var(--navy);padding-top:6px}
.toc li.l3 a{padding-left:18px;color:var(--muted);font-size:.94em}
.toc li a:hover{color:var(--blue)}

h1,h2,h3,h4{color:var(--navy);line-height:1.35;font-weight:700}
h1{font-size:20pt;margin:0 0 6mm}
h2{font-size:16pt;margin:12mm 0 5mm;padding-bottom:2.5mm;border-bottom:2px solid var(--navy);position:relative}
h2::after{content:"";position:absolute;left:0;bottom:-2px;width:22mm;height:2px;background:var(--yellow)}
h3{font-size:12.5pt;margin:8mm 0 3mm;padding-left:3mm;border-left:4px solid var(--blue)}
h4{font-size:11pt;margin:6mm 0 2mm}
p{margin:0 0 3mm}
a{color:var(--navy);text-decoration-color:var(--blue);text-underline-offset:2px}
a.cite{text-decoration:none;color:var(--blue);font-weight:700}
strong{color:var(--navy)}
hr{border:none;border-top:1px solid var(--gray);margin:8mm 0}
ul,ol{margin:0 0 3mm;padding-left:6mm}
li{margin:.6mm 0}
li::marker{color:var(--blue)}
li.ref{scroll-margin-top:12px}
li.ref:target{background:rgba(255,212,92,.35)}
code{font-family:'SF Mono',Menlo,Consolas,monospace;font-size:.88em;background:var(--mist);
  border:1px solid var(--gray);padding:.05em .35em;border-radius:3px}
pre{background:var(--mist);border:1px solid var(--gray);border-radius:6px;padding:4mm;
  overflow-x:auto;font-size:8.6pt;line-height:1.5;white-space:pre-wrap}
pre code{background:none;border:none;padding:0;font-size:inherit}
blockquote{margin:4mm 0;padding:3mm 5mm;background:var(--mist);border-left:4px solid var(--blue);border-radius:0 6px 6px 0}
blockquote p:last-child,blockquote ul:last-child{margin-bottom:0}
.table-wrap{overflow-x:auto;margin:3mm 0 5mm}
table{width:100%;border-collapse:collapse;font-size:9pt;line-height:1.55}
th{background:var(--navy);color:var(--mist);font-weight:700;text-align:left;padding:2.2mm 2.6mm;vertical-align:bottom;
  border-bottom:2px solid var(--yellow)}
td{padding:2mm 2.6mm;border-bottom:1px solid var(--gray);vertical-align:top}
tbody tr:nth-child(even) td{background:var(--mist)}
.mermaid{margin:4mm 0;text-align:center;background:#fff;border:1px solid var(--gray);border-radius:6px;padding:4mm;
  white-space:pre-wrap;font-size:8.6pt}

/* ---------- print ---------- */
@page{size:A4;margin:18mm 17mm 20mm;
  @bottom-center{content:counter(page);font-family:var(--font);font-size:8.5pt;color:#7A8194}}
@page cover{margin:0;@bottom-center{content:none}}
@media print{
  body{background:#fff}
  .cover{page:cover;width:210mm;height:297mm;margin:0;box-shadow:none;break-after:page}
  .sheet{width:auto;margin:0;padding:0;box-shadow:none}
  .toc{break-after:page}
  body.chapter-break .doc h2{break-before:page;margin-top:0}
  h2,h3,h4{break-after:avoid}
  tr,blockquote,pre,.mermaid,li.ref{break-inside:avoid}
  thead{display:table-header-group}
  .table-wrap{overflow:visible}
  a{color:inherit;text-decoration:none}
  a.cite{color:var(--blue)}
}
"""

MERMAID_JS = """<script type="module">
import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
mermaid.initialize({startOnLoad:true,theme:'base',themeVariables:{
  primaryColor:'#F7F8FC',primaryBorderColor:'#6688CC',primaryTextColor:'#0B163F',
  lineColor:'#0B163F',fontFamily:'Pretendard Variable, Pretendard, sans-serif'}});
</script>"""


def em_width(text):
    """표지 제목 한 줄의 대략적인 폭(em). 한글 1, 영문 대문자 0.7, 기타 ASCII 0.62, 공백 0.3."""
    width = 0.0
    for ch in text:
        if ch == " ":
            width += 0.3
        elif ord(ch) < 128:
            width += 0.7 if ch.isupper() else 0.62
        else:
            width += 1.0
    return width


def cover_title_lines(meta):
    """표지 큰 제목의 줄과 글자 크기(cqw)를 정한다. cover_title에 '|'로 줄을 직접 나눌 수 있다."""
    if meta.get("cover_title"):
        lines = [x.strip() for x in meta["cover_title"].split("|") if x.strip()]
    else:
        lines, cur = [], ""
        for word in meta.get("title", "보고서").split():
            cand = f"{cur} {word}".strip()
            if cur and em_width(cand) > 9.0:
                lines.append(cur)
                cur = word
            else:
                cur = cand
        if cur:
            lines.append(cur)
    widest = max(em_width(x) for x in lines) or 1
    return lines, min(11.0, 84.0 / widest)


def build_html(md_text, meta_override, cover_src, font_css, toc_depth, chapter_break):
    meta, body = split_front_matter(md_text)
    meta.update({k: v for k, v in meta_override.items() if v})
    lines = body.splitlines()

    # front matter에 제목이 없으면 첫 '# 제목'과 그 아래 '·' 한 줄을 표지로 옮긴다
    if "title" not in meta:
        for idx, line in enumerate(lines):
            m = re.match(r"^#\s+(.+)$", line)
            if m:
                meta["title"] = m.group(1).strip()
                del lines[idx]
                k = idx
                while k < len(lines) and not lines[k].strip():
                    k += 1
                if (k < len(lines) and "·" in lines[k] and not starts_block(lines[k])
                        and (k + 1 >= len(lines) or not lines[k + 1].strip()) and "meta" not in meta):
                    meta["meta"] = re.sub(r"\*\*(.+?)\*\*", r"\1", lines[k].strip())
                    del lines[k]
                break

    ref_ids = {m.group(1) for m in map(REF_ITEM_RE.match, lines) if m}
    ctx = Context(ref_ids, toc_depth)
    doc_html = parse_blocks(lines, ctx)
    if chapter_break:
        # ## 장은 새 쪽에서 시작하므로 그 앞의 가로줄(---)은 필요 없다.
        # 남겨 두면 목차의 쪽 나눔과 장의 쪽 나눔 사이에 가로줄만 있는 빈 쪽이 생긴다.
        doc_html = re.sub(r"<hr>\s*(?=<h2[ >])", "", doc_html)

    esc = lambda s: html.escape(s or "")
    title = meta.get("title", "보고서")
    # 표지 하단에는 작성 기준일만 쓴다: front matter의 date, 없으면 제목 아래 '·' 줄의 "작성 기준일 YYYY-MM-DD"
    base_date = meta.get("date")
    if not base_date:
        m = re.search(r"작성\s*기준일\s*[:：]?\s*(\d{4}[-.]\d{1,2}[-.]\d{1,2})", meta.get("meta", ""))
        base_date = m.group(1) if m else ""
    lines_, size = cover_title_lines(meta)
    title_html = "<br>".join(esc(x) for x in lines_)
    kicker = meta.get("cover_label", DEFAULT_LABEL)
    title_block = ((f'<p class="cover-kicker">{esc(kicker)}</p>' if kicker else "")
                   + f'<h1 class="cover-title" style="font-size:{size:.2f}cqw">{title_html}</h1>')
    cover = [
        '<section class="cover">',
        f'<img class="cover-bg" src="{cover_src}" alt="">',
        f'<p class="cover-team logo-fit">{esc(meta.get("team") or DEFAULT_TEAM)}</p>',
        f'<div class="cover-title-wrap on-light">{title_block}</div>',
        f'<div class="cover-title-wrap on-dark" aria-hidden="true">{title_block}</div>',
        '<div class="cover-info">',
    ]
    if base_date:
        cover.append(f'<p class="cover-meta logo-fit">{esc(base_date)}</p>')
    cover.append("</div></section>")

    toc_html = ""
    if ctx.toc:
        items = "".join(f'<li class="l{lvl}"><a href="#{hid}">{html.escape(text)}</a></li>' for lvl, text, hid in ctx.toc)
        toc_html = f'<nav class="toc"><h2>목차</h2><ol>{items}</ol></nav>'

    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<style>
{font_css}
{CSS}
</style>
</head>
<body class="{'chapter-break' if chapter_break else ''}">
{''.join(cover)}
<main class="sheet">
{toc_html}
<article class="doc">
{doc_html}
</article>
</main>
{MERMAID_JS if ctx.mermaid else ''}
</body>
</html>
"""


def find_chrome():
    for path in CHROME_PATHS:
        if os.path.isabs(path) and os.path.exists(path):
            return path
        if not os.path.isabs(path) and shutil.which(path):
            return shutil.which(path)
    return None


def make_pdf(html_path, pdf_path):
    chrome = find_chrome()
    if not chrome:
        print("Chrome을 찾지 못해 PDF를 만들지 않았습니다. HTML을 Chrome에서 열고 인쇄 → PDF로 저장하세요.")
        return
    subprocess.run([chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                    "--virtual-time-budget=15000", f"--print-to-pdf={pdf_path}",
                    html_path.resolve().as_uri()], check=True, capture_output=True)
    print(f"PDF: {pdf_path}")


def main():
    ap = argparse.ArgumentParser(description="Markdown 보고서 → 표지가 붙은 HTML")
    ap.add_argument("markdown", type=Path)
    ap.add_argument("-o", "--output", type=Path, help="출력 HTML 경로 (기본: 입력 파일명.html)")
    ap.add_argument("--cover", "--cover-docx", dest="cover", type=Path, default=DEFAULT_COVER,
                    help="표지 이미지(.png·.jpg) 또는 docx (기본: 스크립트 옆 표지.png)")
    ap.add_argument("--single-file", action="store_true", help="표지 이미지를 HTML에 넣어 한 파일로 만든다")
    ap.add_argument("--pdf", action="store_true", help="Chrome으로 PDF도 만든다")
    ap.add_argument("--toc-depth", type=int, default=3, choices=[0, 2, 3], help="목차 깊이 (0: 목차 없음)")
    ap.add_argument("--no-chapter-break", action="store_true", help="인쇄할 때 ## 제목마다 새 쪽으로 넘기지 않는다")
    for key in ("title", "subtitle", "team", "date", "version", "cover-label", "cover-title"):
        ap.add_argument(f"--{key}", help=f"표지 {key} (front matter보다 우선)")
    args = ap.parse_args()

    if not args.markdown.exists():
        sys.exit(f"Markdown 파일이 없습니다: {args.markdown}")
    if not args.cover.exists():
        sys.exit(f"표지 파일이 없습니다: {args.cover} (--cover로 지정)")

    out = args.output or args.markdown.with_suffix(".html")
    out.parent.mkdir(parents=True, exist_ok=True)
    asset_dir = out.parent / f"{out.stem}_assets"
    cover_src, font_css = extract_cover(args.cover, asset_dir, args.single_file)

    override = {"title": args.title, "subtitle": args.subtitle, "team": args.team,
                "date": args.date, "version": args.version, "cover_label": args.cover_label, "cover_title": args.cover_title}
    page = build_html(args.markdown.read_text(encoding="utf-8"), override, cover_src, font_css,
                      args.toc_depth or 1, not args.no_chapter_break)
    out.write_text(page, encoding="utf-8")
    print(f"HTML: {out}" + ("" if args.single_file else f"  (자료: {asset_dir.name}/)"))
    if args.pdf:
        make_pdf(out, out.with_suffix(".pdf"))


if __name__ == "__main__":
    main()
