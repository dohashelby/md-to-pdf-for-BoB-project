#!/usr/bin/env python3
"""Markdown 보고서를 번뜩번뜩 작은별 표지가 붙은 HTML(선택: PDF)로 만든다.

사용법
  python3 make_report_html.py 보고서.md                      → 보고서.html 한 파일(표지 이미지 포함)
  python3 make_report_html.py 보고서.md -o out/report.html
  python3 make_report_html.py 보고서.md --pdf                → 보고서.pdf 한 파일만 생성(Chrome 사용)
  python3 make_report_html.py 보고서.md -o out/report.pdf    → 출력 경로가 .pdf여도 PDF만 생성
  자료 폴더(_assets)는 만들지 않는다. PDF를 만들 때 쓰는 중간 HTML은 임시 폴더에서 만들고 지운다.

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

도표 (레퍼런스: 맥킨지 리포트의 '도표 N' 형식)
  표 바로 위 한 줄에 "도표: 제목"을 쓰면 '도표 N' 라벨과 굵은 제목이 붙는다.
  표 바로 아래 문단이 "출처"·"자료"·"주"·"Note"·"참고"로 시작하면 작은 회색 주석으로 표시한다.
  그래프는 ```chart 블록에 쓴다. 머리 줄(key: value) 다음에 CSV를 적는다.

  ```chart
  type: bar                      (bar: 세로 막대, hbar: 가로 막대)
  title: 하반기 들어 vLLM 보안 권고가 크게 늘었음
  subtitle: vLLM 보안 권고 수
  unit: 건, GHSA ID 기준
  source: GitHub Security Advisories(R67), 2026-10-04 집계
  구분,권고 수
  2026년 1~6월,23
  2026-07-01~10-04,36
  ```
  둘째 열부터는 계열(series)이며, 계열이 둘 이상이면 오른쪽 위에 범례가 생긴다.

다이어그램 (모두 title·subtitle·unit·source 머리 줄을 쓸 수 있다)
  ```flow      가로 흐름. 한 줄에 "이름 | 설명", 이름 끝 *는 강조, 6개 이상이면 두 줄로 접는다.
               aside: 이름 | 설명  → 해당 상자 아래에 보조 설명을 단다.
  ```matrix    2×2. x: 왼쪽 → 오른쪽, y: 아래 → 위, top-left: 제목 | 내용 (나머지 칸도 같은 형식).
               칸 이름 뒤 *는 강조 칸. 내용이 쉼표 목록이면 작은 칩으로 그린다.
  ```steps     번호 카드. 한 줄에 "제목 | 설명", 줄 앞 *는 체크 표시(legend: 체크 설명).
               columns: 3 으로 열 수를 정한다.

상자
  > **해석 범위**  처럼 첫 줄이 굵은 글씨뿐인 인용은 왼쪽 여백에 라벨을 둔 주석으로 그린다.

표준 라이브러리만 사용한다(Python 3.9+). PDF 생성에는 Google Chrome이 필요하다.
"""

import argparse
import base64
import html
import math
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
        self.exhibit = 0
        self.pending_caption = ""
        self.mermaid = False

    def heading(self, level, raw):
        self.count += 1
        hid = f"s{self.count}"
        kicker, title = "", raw
        if level == 2:
            # "## 1. 제목" → 작은 'Chapter 1' 라벨 + 큰 제목, "## 부록 A. 제목" → '부록 A' 라벨 + 제목
            m = re.match(r"^(\d+)\.\s+(.+)$", raw)
            m2 = re.match(r"^(부록\s+\S+?)\.\s*(.+)$", raw)
            if m:
                kicker, title = f"Chapter {m.group(1)}", m.group(2)
            elif m2:
                kicker, title = m2.group(1), m2.group(2)
        text = inline(title, self)
        if 2 <= level <= self.toc_depth:
            self.toc.append((level, kicker, re.sub(r"<[^>]+>", "", text), hid))
        if level == 2:
            label = f'<span class="kicker">{html.escape(kicker)}</span>' if kicker else ""
            return f'<h2 id="{hid}" class="chapter">{label}{text}</h2>'
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


CAPTION_RE = re.compile(r"^(?:도표|Table)\s*[:：]\s*(.+)$")
NOTE_RE = re.compile(r"^\**(출처|자료|주|Note|참고)(\s*[:：)]|는\s)")
CHART_KEYS = ("type", "title", "subtitle", "unit", "source", "note")
CHART_COLORS = ["#0B163F", "#6688CC", "#FFD45C", "#9AA6C4"]


def exhibit(ctx, title, body, notes=(), sub=""):
    """레퍼런스의 도표 형식: 작은 '도표 N' 라벨, 굵은 제목, 본체, 작은 회색 주석."""
    head = ""
    if title:
        ctx.exhibit += 1
        head = (f'<p class="ex-label">도표 {ctx.exhibit}</p>'
                f'<p class="ex-title">{inline(title, ctx)}</p>')
    foot = "".join(f'<p class="ex-note">{inline(n, ctx)}</p>' for n in notes if n)
    return f'<figure class="exhibit">{head}{sub}{body}{foot}</figure>'


def to_num(text):
    try:
        return max(0.0, float(re.sub(r"[^\d.\-]", "", text)))
    except ValueError:
        return 0.0


def text_w(text, size):
    """SVG 글자 폭 추정(한글 1em, 그 밖 0.6em)."""
    return sum(size if ord(c) > 127 else size * 0.6 for c in text)


def svg_text(x, y, text, size=15, anchor="middle", weight=400, fill="#1D2433"):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}" '
            f'font-weight="{weight}" fill="{fill}">{html.escape(text)}</text>')


def render_chart(code, ctx):
    """```chart 블록을 레퍼런스 스타일의 막대그래프(SVG)로 그린다."""
    spec, rows = {}, []
    for line in code.splitlines():
        if not line.strip():
            continue
        m = re.match(r"^\s*(" + "|".join(CHART_KEYS) + r")\s*:\s*(.*)$", line)
        if m and not rows:
            spec[m.group(1)] = m.group(2).strip()
        else:
            rows.append([c.strip() for c in line.split(",")])
    if len(rows) < 2 or len(rows[0]) < 2:
        return f'<pre><code>{html.escape(code)}</code></pre>'

    series, cats = rows[0][1:], [r[0] for r in rows[1:]]
    raw = [[(r[j + 1] if j + 1 < len(r) else "") for j in range(len(series))] for r in rows[1:]]
    vals = [[to_num(v) for v in row] for row in raw]
    top_v = max(max(row) for row in vals) or 1
    m_ = len(series)
    W, parts = 1000, []

    legend_h = 0
    if m_ > 1:
        legend_h, x = 40, W
        for j in reversed(range(m_)):
            x -= text_w(series[j], 15)
            parts.append(svg_text(x, 18, series[j], 15, "start"))
            x -= 24
            parts.append(f'<rect x="{x:.1f}" y="5" width="16" height="16" fill="{CHART_COLORS[j % 4]}"/>')
            x -= 22

    if spec.get("type", "bar") == "hbar":
        label_w, bar_h, gap = 300, 26, 5
        avail = W - label_w - 90
        y = legend_h + 6
        for i, cat in enumerate(cats):
            block = m_ * bar_h + (m_ - 1) * gap
            parts.append(svg_text(label_w - 16, y + block / 2 + 5, cat, 15, "end", 600, "#0B163F"))
            for j in range(m_):
                length = vals[i][j] / top_v * avail
                by = y + j * (bar_h + gap)
                parts.append(f'<rect x="{label_w}" y="{by:.1f}" width="{length:.1f}" height="{bar_h}" fill="{CHART_COLORS[j % 4]}"/>')
                parts.append(svg_text(label_w + length + 8, by + bar_h / 2 + 5, raw[i][j], 15, "start", 600))
            y += block + 22
        parts.append(f'<line x1="{label_w}" y1="{legend_h}" x2="{label_w}" y2="{y - 16:.1f}" stroke="#0B163F" stroke-width="1.5"/>')
        H = y
    else:
        top, plot_h = legend_h + 34, 240
        group = W / len(cats)
        bar_w = min(90, group * 0.62 / m_)
        gap = 10 if m_ > 1 else 0
        for i, cat in enumerate(cats):
            x0 = group * (i + 0.5) - (m_ * bar_w + (m_ - 1) * gap) / 2
            for j in range(m_):
                h = vals[i][j] / top_v * plot_h
                bx = x0 + j * (bar_w + gap)
                parts.append(f'<rect x="{bx:.1f}" y="{top + plot_h - h:.1f}" width="{bar_w:.1f}" height="{h:.1f}" fill="{CHART_COLORS[j % 4]}"/>')
                parts.append(svg_text(bx + bar_w / 2, top + plot_h - h - 9, raw[i][j], 16, "middle", 600))
            parts.append(svg_text(group * (i + 0.5), top + plot_h + 30, cat, 15))
        parts.append(f'<line x1="0" y1="{top + plot_h}" x2="{W}" y2="{top + plot_h}" stroke="#0B163F" stroke-width="1.5"/>')
        H = top + plot_h + 46

    svg = (f'<svg class="chart" viewBox="0 0 {W} {H:.0f}" role="img" '
           f'aria-label="{html.escape(spec.get("subtitle") or spec.get("title") or "그래프")}">{"".join(parts)}</svg>')
    sub = ""
    if spec.get("subtitle") or spec.get("unit"):
        sub = (f'<p class="ex-sub"><strong>{html.escape(spec.get("subtitle", ""))}</strong>'
               f'{html.escape(spec.get("unit", ""))}</p>')
    notes = [f'자료: {spec["source"]}' if spec.get("source") else "", spec.get("note", "")]
    return exhibit(ctx, spec.get("title", ""), svg, notes, sub).replace('class="exhibit"', 'class="exhibit chart-fig"', 1)


def parse_spec(code, keys):
    """다이어그램 블록: 'key: value' 머리 줄과 나머지 항목 줄을 나눈다. key 뒤 *는 강조 표시."""
    spec, items = {}, []
    for line in code.splitlines():
        if not line.strip():
            continue
        m = re.match(r"^\s*([a-z][\w-]*\*?)\s*:\s*(.*)$", line)
        if m and m.group(1).rstrip("*") in keys:
            spec[m.group(1)] = m.group(2).strip()
        else:
            items.append(line.strip())
    return spec, items


def sub_html(spec):
    if not (spec.get("subtitle") or spec.get("unit")):
        return ""
    return (f'<p class="ex-sub"><strong>{html.escape(spec.get("subtitle", ""))}</strong>'
            f'{html.escape(spec.get("unit", ""))}</p>')


def figure(ctx, spec, svg_body, w, h, label):
    svg = (f'<svg class="chart" viewBox="0 0 {w} {h:.0f}" role="img" aria-label="{html.escape(label)}">'
           f'{svg_body}</svg>')
    notes = [f'자료: {spec["source"]}' if spec.get("source") else "", spec.get("note", "")]
    return exhibit(ctx, spec.get("title", ""), svg, notes, sub_html(spec)).replace(
        'class="exhibit"', 'class="exhibit chart-fig"', 1)


def wrap(text, max_w, size):
    """SVG 글자 줄바꿈(단어 단위, 너무 긴 단어는 글자 단위)."""
    # 띄어쓰기 외에 가운뎃점(·)·쉼표 뒤에서도 줄을 바꿀 수 있게 토큰을 나눈다
    tokens = []
    for word in text.split():
        parts = [x for x in re.split(r"(?<=[·,/])", word) if x]
        tokens += [(part, j > 0) for j, part in enumerate(parts)]
    lines, cur = [], ""
    for tok, attach in tokens:
        cand = (cur + tok) if attach else f"{cur} {tok}".strip()
        if cur and text_w(cand, size) > max_w:
            lines.append(cur)
            cur = tok
        else:
            cur = cand
    lines.append(cur)
    out = []
    for line in lines:
        while text_w(line, size) > max_w and len(line) > 1:
            k = len(line)
            while k > 1 and text_w(line[:k], size) > max_w:
                k -= 1
            out.append(line[:k])
            line = line[k:]
        out.append(line)
    return [x for x in out if x]


def text_lines(x, y, lines, size, lh, anchor="start", weight=400, fill="#1D2433"):
    return "".join(svg_text(x, y + i * lh, t, size, anchor, weight, fill) for i, t in enumerate(lines))


def arrow(x1, y1, x2, y2, color="#0B163F", width=1.6, head=9, dash=""):
    ang = math.atan2(y2 - y1, x2 - x1)
    bx, by = x2 - head * math.cos(ang), y2 - head * math.sin(ang)
    px, py = -math.sin(ang) * head * 0.55, math.cos(ang) * head * 0.55
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{bx:.1f}" y2="{by:.1f}" stroke="{color}" stroke-width="{width}"{d}/>'
            f'<polygon points="{x2:.1f},{y2:.1f} {bx + px:.1f},{by + py:.1f} {bx - px:.1f},{by - py:.1f}" fill="{color}"/>')


NAVY, BLUE, YELLOW, MIST, GRAY, MUTED = "#0B163F", "#6688CC", "#FFD45C", "#F7F8FC", "#E5E7EB", "#5A6378"


def render_flow(code, ctx):
    """```flow: 상자와 화살표로 그린 가로 흐름. 6개 이상이면 두 줄로 접는다."""
    spec, items = parse_spec(code, ("title", "subtitle", "unit", "source", "note", "aside"))
    nodes = []
    for item in items:
        name, _, desc = (x.strip() for x in item.partition("|"))
        nodes.append((name.rstrip("*").strip(), desc, name.endswith("*")))
    if not nodes:
        return f"<pre><code>{html.escape(code)}</code></pre>"
    W, gap_x, row_gap = 1000, 44, 64
    per = len(nodes) if len(nodes) <= 5 else math.ceil(len(nodes) / 2)
    bw = (W - (per - 1) * gap_x) / per
    pad = 18
    wrapped = [(wrap(n, bw - 2 * pad, 18.5), wrap(d, bw - 2 * pad, 15.5)) for n, d, _ in nodes]
    bh = max(2 * pad + len(a) * 24 + (8 + len(b) * 22 if b else 0) for a, b in wrapped) + 4
    aside_name, _, aside_text = (x.strip() for x in spec.get("aside", "").partition("|"))
    parts, pos = [], []
    for i, ((name, desc, hl), (nl, dl)) in enumerate(zip(nodes, wrapped)):
        r, c = divmod(i, per)
        x, y = c * (bw + gap_x), r * (bh + row_gap)
        pos.append((x, y))
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh:.1f}" fill="{NAVY if hl else MIST}"/>')
        parts.append(text_lines(x + pad, y + pad + 18, nl, 18.5, 24, weight=800, fill=MIST if hl else NAVY))
        if dl:
            parts.append(text_lines(x + pad, y + pad + 18 + len(nl) * 24 + 6, dl, 15.5, 22,
                                    fill="#C9D2EA" if hl else MUTED))
    for i in range(len(nodes) - 1):
        (x1, y1), (x2, y2) = pos[i], pos[i + 1]
        if y1 == y2:
            parts.append(arrow(x1 + bw + 6, y1 + bh / 2, x2 - 6, y2 + bh / 2))
        else:  # 줄을 바꿀 때는 아래로 꺾어 다음 줄 첫 상자로 잇는다
            mid = y1 + bh + row_gap / 2
            parts.append(f'<polyline points="{x1 + bw / 2:.1f},{y1 + bh + 4:.1f} {x1 + bw / 2:.1f},{mid:.1f} '
                         f'{x2 + bw / 2:.1f},{mid:.1f}" fill="none" stroke="{NAVY}" stroke-width="1.6"/>')
            parts.append(arrow(x2 + bw / 2, mid, x2 + bw / 2, y2 - 4))
    H = pos[-1][1] + bh
    names = [n for n, _, _ in nodes]
    if aside_name in names:
        x, y = pos[names.index(aside_name)]
        cx = x + bw / 2
        parts.append(arrow(cx, y + bh + 38, cx, y + bh + 6, BLUE, 1.4, 8, "4 3"))
        lines = wrap(aside_text, max(bw * 1.6, 260), 15.5)
        parts.append(text_lines(cx, y + bh + 60, lines, 15.5, 22, "middle", 600, NAVY))
        H = max(H, y + bh + 60 + (len(lines) - 1) * 22 + 8)
    return figure(ctx, spec, "".join(parts), W, H, spec.get("title") or "흐름도")


def render_matrix(code, ctx):
    """```matrix: 2×2 포지셔닝. 강조 칸(*)은 네이비로 채우고 노란 별을 붙인다."""
    cells_keys = ("top-left", "top-right", "bottom-left", "bottom-right")
    spec, _ = parse_spec(code, ("title", "subtitle", "unit", "source", "note", "x", "y") + cells_keys)
    split = lambda v: [t.strip() for t in re.split(r"→|->", v)] + ["", ""]
    xs, ys = split(spec.get("x", "")), split(spec.get("y", ""))
    W, L, top, gap, pad = 1000, 170, 58, 12, 22
    cw = (W - L - gap) / 2

    def content(key):
        hl = f"{key}*" in spec
        text = spec.get(f"{key}*") or spec.get(key) or ""
        head, _, body = (t.strip() for t in text.partition("|")) if "|" in text else ("", "", text.strip())
        head_lines = wrap(("★ " if hl else "") + head, cw - 2 * pad, 19) if head else []
        chips = [t.strip() for t in body.split(",")] if body.count(",") >= 1 and len(body) < 400 else []
        body_lines = [] if chips else wrap(body, cw - 2 * pad, 16)
        rows_, x, row = [], 0, []
        for chip in chips:  # 칩 줄바꿈
            w = text_w(chip, 15) + 26
            if row and x + w > cw - 2 * pad:
                rows_.append(row)
                row, x = [], 0
            row.append((chip, w))
            x += w + 8
        if row:
            rows_.append(row)
        h = 2 * pad + len(head_lines) * 26 + (10 if head_lines and (rows_ or body_lines) else 0)
        h += len(rows_) * 40 + len(body_lines) * 25
        return hl, head_lines, rows_, body_lines, h

    data = {k: content(k) for k in cells_keys}
    rh_top = max(150, data["top-left"][4], data["top-right"][4])
    rh_bot = max(150, data["bottom-left"][4], data["bottom-right"][4])
    parts = []
    # 열 머리와 가로축 화살표
    for i, label in enumerate(xs[:2]):
        parts.append(svg_text(L + i * (cw + gap) + cw / 2, 24, label, 16, "middle", 800, NAVY))
    parts.append(arrow(L, 40, W, 40, NAVY, 1.4, 9))
    # 행 머리와 세로축 화살표
    rows_y = [(top, rh_top, ys[1]), (top + rh_top + gap, rh_bot, ys[0])]
    for y, h, label in rows_y:
        lines = wrap(label, L - 44, 16)
        parts.append(text_lines(28, y + h / 2 - (len(lines) - 1) * 11 + 5, lines, 16, 22, weight=800, fill=NAVY))
    parts.append(arrow(10, top + rh_top + gap + rh_bot, 10, top, NAVY, 1.4, 9))
    for idx, key in enumerate(cells_keys):
        r, c = divmod(idx, 2)
        x, (y, h, _) = L + c * (cw + gap), rows_y[r]
        hl, head_lines, chip_rows, body_lines, _ = data[key]
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{cw:.1f}" height="{h:.1f}" fill="{NAVY if hl else MIST}"/>')
        cy = y + pad + 18
        for t in head_lines:
            if hl and t.startswith("★ "):
                parts.append(f'<text x="{x + pad:.1f}" y="{cy:.1f}" font-size="18" font-weight="800" fill="{MIST}">'
                             f'<tspan fill="{YELLOW}">★</tspan> {html.escape(t[2:])}</text>')
            else:
                parts.append(svg_text(x + pad, cy, t, 18, "start", 800, MIST if hl else NAVY))
            cy += 26
        if head_lines:
            cy += 10
        for row in chip_rows:
            cx = x + pad
            for chip, w in row:
                parts.append(f'<rect x="{cx:.1f}" y="{cy - 21:.1f}" width="{w:.1f}" height="31" rx="15.5" '
                             f'fill="{"#1B2A5C" if hl else "#FFFFFF"}" stroke="{"#33467A" if hl else GRAY}"/>')
                parts.append(svg_text(cx + w / 2, cy, chip, 15, "middle", 600, MIST if hl else NAVY))
                cx += w + 8
            cy += 40
        parts.append(text_lines(x + pad, cy, body_lines, 16, 25, fill="#C9D2EA" if hl else "#1D2433"))
    H = top + rh_top + gap + rh_bot + 4
    return figure(ctx, spec, "".join(parts), W, H, spec.get("title") or "2×2 매트릭스")


def render_steps(code, ctx):
    """```steps: 큰 번호를 단 카드. 줄 앞 *는 체크 표시."""
    spec, items = parse_spec(code, ("title", "subtitle", "unit", "source", "note", "legend", "columns"))
    cols = max(1, int(spec.get("columns", "3")))
    W, gap, pad = 1000, 16, 22
    cw = (W - (cols - 1) * gap) / cols
    cards = []
    for item in items:
        checked = item.startswith("*")
        head, _, desc = (t.strip() for t in item.lstrip("*").partition("|"))
        cards.append((checked, wrap(head, cw - 2 * pad - 30, 19), wrap(desc, cw - 2 * pad, 15.5)))
    if not cards:
        return f"<pre><code>{html.escape(code)}</code></pre>"
    legend_h = 36 if any(c[0] for c in cards) else 0
    parts = []
    if legend_h:
        label = spec.get("legend", "우리 프레임워크가 지원하는 단계")
        lx = W - text_w(label, 15)
        parts.append(svg_text(lx, 18, label, 15, "start", 400, MUTED))
        parts.append(f'<circle cx="{lx - 16:.1f}" cy="13" r="10" fill="{NAVY}"/>'
                     f'<path d="M{lx - 21:.1f},13 l3.5,3.5 l6.5,-7" fill="none" stroke="{MIST}" stroke-width="2"/>')
    y = legend_h
    for start in range(0, len(cards), cols):
        row = cards[start:start + cols]
        h = max(2 * pad + 46 + len(t) * 25 + 8 + len(d) * 22 for _, t, d in row)
        for j, (checked, t, d) in enumerate(row):
            x = j * (cw + gap)
            parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{cw:.1f}" height="{h:.1f}" fill="{MIST}"/>')
            parts.append(svg_text(x + pad, y + pad + 32, str(start + j + 1), 36, "start", 800, BLUE))
            if checked:
                cx, cy = x + cw - 26, y + 26
                parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="12" fill="{NAVY}"/>'
                             f'<path d="M{cx - 6:.1f},{cy:.1f} l4,4 l8,-8.5" fill="none" stroke="{MIST}" stroke-width="2.2"/>')
            parts.append(text_lines(x + pad, y + pad + 46 + 19, t, 19, 25, weight=800, fill=NAVY))
            parts.append(text_lines(x + pad, y + pad + 46 + 19 + len(t) * 25 + 6, d, 15.5, 22, fill=MUTED))
        y += h + gap
    return figure(ctx, spec, "".join(parts), W, y - gap, spec.get("title") or "단계")


def is_table_start(lines, k):
    return k + 1 < len(lines) and lines[k].lstrip().startswith("|") and bool(TABLE_SEP_RE.match(lines[k + 1]))


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
            if lang == "chart":
                out.append(render_chart(code, ctx))
            elif lang in ("flow", "matrix", "steps"):
                out.append({"flow": render_flow, "matrix": render_matrix, "steps": render_steps}[lang](code, ctx))
            elif lang == "mermaid":
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
            notes = []
            k = i
            while k < n and not lines[k].strip():
                k += 1
            if k < n and NOTE_RE.match(lines[k].strip()) and not starts_block(lines[k]):
                buf = []
                while k < n and lines[k].strip() and not starts_block(lines[k]):
                    buf.append(lines[k].strip())
                    k += 1
                notes, i = [" ".join(buf)], k
            caption, ctx.pending_caption = ctx.pending_caption, ""
            out.append(exhibit(ctx, caption, render_table(rows, sep, ctx), notes))
            continue

        if line.lstrip().startswith(">"):
            buf = []
            while i < n and lines[i].lstrip().startswith(">"):
                s = lines[i].lstrip()[1:]
                buf.append(s[1:] if s.startswith(" ") else s)
                i += 1
            # 첫 줄이 굵은 글씨뿐이면(> **해석 범위**) 왼쪽 여백에 라벨을 둔 주석으로 그린다
            label = ""
            first = next((k for k, l in enumerate(buf) if l.strip()), None)
            if first is not None:
                lm = re.match(r"^\*\*(.+?)\*\*\s*$", buf[first].strip())
                if lm:
                    label = lm.group(1)
                    buf = buf[:first] + buf[first + 1:]
            label_html = f'<div class="note-label">{inline(label, ctx)}</div>' if label else '<div class="note-label"></div>'
            out.append(f'<aside class="note">{label_html}<div class="note-body">{parse_blocks(buf, ctx)}</div></aside>')
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
        k = i
        while k < n and not lines[k].strip():
            k += 1
        cap = CAPTION_RE.match(" ".join(buf))
        if cap and len(buf) == 1 and is_table_start(lines, k):
            ctx.pending_caption = cap.group(1)
            continue
        out.append("<p>" + inline(" ".join(buf), ctx) + "</p>")
    return "\n".join(out)


# ---------------------------------------------------------------- cover assets

def extract_cover(cover):
    """표지 이미지(.png·.jpg) 또는 docx에서 배경 이미지를 꺼내 HTML에 바로 넣을 data URI로 만든다."""
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

    return f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}", ""


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
  --text:#1D2433; --muted:#5A6378; --indent:30mm;
  /* 표지.png 기준 위치(폭 대비 %): 크림·네이비 경계, BBLS 로고의 왼쪽 끝과 폭 */
  --split:36.209%; --logo-left:3.79%; --logo-width:28.53%;
  --font:'Pretendard Variable',Pretendard,-apple-system,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;
}
*{box-sizing:border-box}
html{-webkit-print-color-adjust:exact;print-color-adjust:exact}
body{margin:0;background:var(--gray);color:var(--text);
  font-family:var(--font);
  font-size:9.6pt;line-height:1.8;word-break:keep-all;overflow-wrap:break-word}

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

/* ---------- body sheet (레퍼런스: 들여 쓴 좁은 본문 단, 쪽 폭을 쓰는 도표) ---------- */
.sheet{width:min(210mm,100%);margin:24px auto 48px;background:#fff;padding:22mm 18mm 24mm;
  box-shadow:0 2px 16px rgba(11,22,63,.10);font-size:9.6pt;line-height:1.8}
.doc > *, .toc{margin-left:var(--indent)}
.doc > .exhibit, .doc > pre, .doc > .mermaid{margin-left:0}
@media screen and (max-width:760px){.doc > *, .toc{margin-left:0}}

.toc-title{font-size:30pt;font-weight:800;color:var(--navy);margin:0 0 16mm;letter-spacing:-.02em;line-height:1.2}
.toc ol{list-style:none;padding:0;margin:0}
.toc li{margin:0 0 6mm}
.toc li a{display:block;color:var(--navy);text-decoration:none}
.toc .t-kicker{display:block;font-size:9pt;font-weight:700;color:var(--text);margin-bottom:.6mm}
.toc .t-title{display:block;font-size:13pt;font-weight:800;line-height:1.35;letter-spacing:-.01em}
.toc li.l3{margin:-3.5mm 0 4.5mm}
.toc li.l3 .t-title{font-size:9.5pt;font-weight:500;color:var(--muted)}
.toc li a:hover .t-title{color:var(--blue)}

h1,h2,h3,h4{color:var(--navy);font-weight:800;letter-spacing:-.015em}
h1{font-size:22pt;line-height:1.3;margin:0 0 8mm}
h2.chapter{font-size:24pt;line-height:1.3;margin-top:14mm;margin-bottom:12mm}
h2.chapter .kicker{display:block;font-size:11pt;font-weight:700;color:var(--navy);letter-spacing:0;margin-bottom:3mm}
h2.chapter .kicker::before{content:"";display:inline-block;width:7mm;height:2.5px;background:var(--yellow);
  vertical-align:middle;margin:-2px 2.5mm 0 0}
h3{font-size:13pt;line-height:1.4;margin:10mm 0 3.5mm}
h4{font-size:10.5pt;line-height:1.4;margin:7mm 0 2mm}
p{margin:0 0 3.4mm}
a{color:var(--navy);text-decoration-color:var(--blue);text-underline-offset:2px}
a.cite{text-decoration:none;color:var(--blue);font-weight:700;font-size:.92em}
strong{color:var(--navy);font-weight:700}
hr{border:none;border-top:1px solid var(--gray);margin:9mm 0}
ul,ol{margin:0 0 3.4mm;padding-left:5.5mm}
li{margin:.8mm 0}
li::marker{color:var(--navy)}
li.ref{scroll-margin-top:12px}
li.ref:target{background:rgba(255,212,92,.35)}
code{font-family:'SF Mono',Menlo,Consolas,monospace;font-size:.86em;background:var(--mist);
  border:1px solid var(--gray);padding:.05em .35em;border-radius:2px}
pre{background:var(--mist);border:none;border-radius:0;padding:5mm 6mm;margin:6mm 0 7mm;
  overflow-x:auto;font-size:8.4pt;line-height:1.55;white-space:pre-wrap}
pre code{background:none;border:none;padding:0;font-size:inherit}
blockquote{margin:6mm 0;padding:4.5mm 6mm;background:var(--mist);border-left:3px solid var(--blue)}
blockquote p:last-child,blockquote ul:last-child{margin-bottom:0}

/* 여백 주석(> **라벨**): 라벨은 왼쪽 들여쓰기 공간에, 내용은 위아래 가는 선 사이에 */
.doc > aside.note{display:grid;grid-template-columns:var(--indent) 1fr;margin:7mm 0 8mm}
.note-label{padding:2.4mm 4mm 0 0;font-size:8.6pt;font-weight:800;line-height:1.45;color:var(--navy)}
.note-label:not(:empty)::before{content:"";display:block;width:6mm;height:2.5px;background:var(--yellow);margin-bottom:2mm}
.note-body{border-top:1.5px solid var(--navy);border-bottom:1px solid var(--gray);padding:2.6mm 0 2.4mm;
  font-size:8.8pt;line-height:1.75;color:#3A4256}
.note-body p,.note-body ul,.note-body ol{margin-bottom:1.6mm}
.note-body > :last-child{margin-bottom:0}
.note-body ul{list-style:none;padding-left:0}
.note-body ul > li{position:relative;padding-left:4.5mm;margin:.6mm 0}
.note-body ul > li::before{content:"–";position:absolute;left:0;color:var(--navy);font-weight:700}
@media screen and (max-width:760px){.doc > aside.note{grid-template-columns:1fr}.note-label{padding:0 0 1.5mm}}

/* 도표: 작은 라벨 → 굵은 제목 → 본체 → 작은 회색 주석 */
.exhibit{margin:9mm 0 10mm;padding:0}
.ex-label{margin:0 0 1.2mm;font-size:8.5pt;color:var(--muted)}
.ex-title{margin:0 0 6mm;font-size:13pt;font-weight:800;line-height:1.42;color:var(--navy);letter-spacing:-.015em}
.ex-sub{margin:0 0 4mm;font-size:9pt;line-height:1.45;color:var(--text)}
.ex-sub strong{display:block;font-weight:800}
.ex-note{margin:2.6mm 0 0;font-size:7.8pt;line-height:1.6;color:var(--muted)}
.ex-note + .ex-note{margin-top:.6mm}
.chart{display:block;width:100%;height:auto;font-family:var(--font);overflow:visible}

/* 표: 칠하지 않은 얇은 가로줄, 굵은 머리글 + 진한 선, 굵은 첫 열 */
.table-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:8.8pt;line-height:1.58}
th{text-align:left;font-weight:800;color:var(--navy);padding:0 3.5mm 2.4mm 0;
  border-bottom:1.5px solid var(--navy);vertical-align:bottom;background:none}
td{padding:2.8mm 3.5mm 2.8mm 0;border-bottom:1px solid var(--gray);vertical-align:top}
td:first-child{font-weight:700;color:var(--navy)}
td strong{font-weight:800}
.mermaid{margin:6mm 0 7mm;text-align:center;background:var(--mist);padding:5mm;white-space:pre-wrap;font-size:8.4pt}

/* ---------- print ---------- */
@page{size:A4;margin:20mm 18mm 22mm;
  @bottom-left{content:"__RUNNING_TITLE__";font-family:'Pretendard Variable',Pretendard,sans-serif;
    font-size:7.5pt;font-weight:700;color:#0B163F}
  @bottom-right{content:counter(page);font-family:'Pretendard Variable',Pretendard,sans-serif;
    font-size:7.5pt;color:#0B163F}}
@page cover{margin:0;@bottom-left{content:none}@bottom-right{content:none}}
@media print{
  body{background:#fff}
  .cover{page:cover;width:210mm;height:297mm;margin:0;box-shadow:none;break-after:page}
  .sheet{width:auto;margin:0;padding:0;box-shadow:none}
  .toc{break-after:page}
  body.chapter-break .doc h2.chapter{break-before:page;margin-top:0}
  h2,h3,h4,.ex-label,.ex-title,.ex-sub{break-after:avoid}
  tr,blockquote,pre,.mermaid,li.ref,.chart-fig,aside.note{break-inside:avoid}
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
        items = "".join(
            f'<li class="l{lvl}"><a href="#{hid}">'
            + (f'<span class="t-kicker">{html.escape(kicker)}</span>' if kicker else "")
            + f'<span class="t-title">{html.escape(text)}</span></a></li>'
            for lvl, kicker, text, hid in ctx.toc)
        toc_html = f'<nav class="toc"><h2 class="toc-title">목차</h2><ol>{items}</ol></nav>'
    running = title.replace("\\", "\\\\").replace('"', '\\"')

    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<style>
{font_css}
{CSS.replace("__RUNNING_TITLE__", running)}
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


def make_pdf(page, pdf_path):
    """HTML을 임시 폴더에 써서 Chrome으로 PDF를 만들고, 임시 파일은 지운다. 성공하면 True."""
    chrome = find_chrome()
    if not chrome:
        return False
    with tempfile.TemporaryDirectory() as tmp:
        html_path = Path(tmp) / "report.html"
        html_path.write_text(page, encoding="utf-8")
        subprocess.run([chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                        "--virtual-time-budget=15000", f"--print-to-pdf={pdf_path.resolve()}",
                        html_path.as_uri()], check=True, capture_output=True)
    return True


def main():
    ap = argparse.ArgumentParser(description="Markdown 보고서 → 표지가 붙은 HTML")
    ap.add_argument("markdown", type=Path)
    ap.add_argument("-o", "--output", type=Path, help="출력 경로 (기본: 입력 파일명.html, --pdf면 .pdf)")
    ap.add_argument("--cover", "--cover-docx", dest="cover", type=Path, default=DEFAULT_COVER,
                    help="표지 이미지(.png·.jpg) 또는 docx (기본: 스크립트 옆 표지.png)")
    ap.add_argument("--single-file", action="store_true", help=argparse.SUPPRESS)  # 예전 옵션: 이제 항상 한 파일
    ap.add_argument("--pdf", action="store_true", help="HTML 대신 PDF 한 파일만 만든다(Chrome 사용)")
    ap.add_argument("--toc-depth", type=int, default=2, choices=[0, 2, 3], help="목차 깊이 (2: 장만, 3: 절까지, 0: 목차 없음)")
    ap.add_argument("--no-chapter-break", action="store_true", help="인쇄할 때 ## 제목마다 새 쪽으로 넘기지 않는다")
    for key in ("title", "subtitle", "team", "date", "version", "cover-label", "cover-title"):
        ap.add_argument(f"--{key}", help=f"표지 {key} (front matter보다 우선)")
    args = ap.parse_args()

    if not args.markdown.exists():
        sys.exit(f"Markdown 파일이 없습니다: {args.markdown}")
    if not args.cover.exists():
        sys.exit(f"표지 파일이 없습니다: {args.cover} (--cover로 지정)")

    want_pdf = args.pdf or (args.output is not None and args.output.suffix.lower() == ".pdf")
    out = args.output or args.markdown
    out = out.with_suffix(".pdf" if want_pdf else ".html")
    out.parent.mkdir(parents=True, exist_ok=True)
    cover_src, font_css = extract_cover(args.cover)

    override = {"title": args.title, "subtitle": args.subtitle, "team": args.team,
                "date": args.date, "version": args.version, "cover_label": args.cover_label, "cover_title": args.cover_title}
    page = build_html(args.markdown.read_text(encoding="utf-8"), override, cover_src, font_css,
                      args.toc_depth or 1, not args.no_chapter_break)
    if not want_pdf:
        out.write_text(page, encoding="utf-8")
        print(f"HTML: {out}")
    elif make_pdf(page, out):
        print(f"PDF: {out}")
    else:
        fallback = out.with_suffix(".html")
        fallback.write_text(page, encoding="utf-8")
        print(f"Chrome을 찾지 못해 PDF 대신 HTML을 만들었습니다: {fallback}\n"
              "Chrome에서 열고 인쇄 → PDF로 저장하세요.")


if __name__ == "__main__":
    main()
