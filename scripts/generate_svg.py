"""ascii_art.json + stats.json → profile-dark.svg / profile-light.svg 생성.

neofetch 스타일 카드: 좌측 터미널 아트 아바타, 우측 시스템 정보 패널.
아트는 ascii_art.json의 style 필드에 따라 두 방식으로 렌더링한다:
  - ascii:     밀도 램프 문자 + 지배색
  - halfblock: ▀▄█ 블록 문자로 셀당 상/하 2픽셀 (원본 픽셀아트에 근접)
모든 tspan에 x/textLength를 명시해 폰트 메트릭과 무관하게 컬럼을 고정한다.
"""
import json
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ART_PATH = ROOT / "ascii_art.json"
STATS_PATH = ROOT / "stats.json"

# ── 레이아웃 상수 ──────────────────────────────────────────
PAD = 30
ART_CW = 6.6
ASCII_FONT, ASCII_LH = 11, 13.0
BLOCK_FONT, BLOCK_LH = 13.4, 13.2  # 블록 글리프가 행을 빈틈없이 채우도록 LH≈2×CW
PANEL_FONT, PANEL_CW, PANEL_LH = 13, 7.8, 20.0
PANEL_COLS = 58
GAP = 34  # 아트 ↔ 패널 간격

# 블록 문자(U+2580/2584/2588) 커버리지가 확실한 폰트 우선
FONT_STACK = "Menlo,Consolas,'DejaVu Sans Mono','SFMono-Regular','Liberation Mono',monospace"

THEMES = {
    "dark": {
        "bg": "#0d1117", "border": "#30363d",
        "title": "#58a6ff", "key": "#ffa657", "val": "#c9d1d9",
        "dim": "#484f58", "header": "#58a6ff",
        "add": "#3fb950", "del": "#f85149",
    },
    "light": {
        "bg": "#ffffff", "border": "#d0d7de",
        "title": "#0969da", "key": "#953800", "val": "#24292f",
        "dim": "#b6bdc7", "header": "#0969da",
        "add": "#1a7f37", "del": "#cf222e",
    },
}


def adjust_color(hex_color: str, theme: str, style: str) -> str:
    """아트 색상을 테마 배경에서 보이도록 보정. 블록은 면이 넓어 보정을 최소화."""
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    if style == "halfblock":
        if theme == "dark" and lum < 35:  # 카드 배경(#0d1117)에 묻히는 극암부만 살짝
            scale = 35 / max(lum, 1)
            r, g, b = (min(255, int(c * scale)) for c in (r, g, b))
        elif theme == "light" and lum > 215:  # 흰 배경에서 사라지는 극명부만 살짝
            r, g, b = (int(c * 0.88) for c in (r, g, b))
    else:
        if theme == "dark":  # 가는 획이라 강하게: 전체 부스트 + 극암부 바닥값
            scale = max(1.35, min(2.4, 65 / max(lum, 1)))
            r, g, b = (min(255, int(c * scale)) for c in (r, g, b))
        else:
            scale = 0.85 - 0.38 * (lum / 255)
            r, g, b = (int(c * scale) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def uptime_text(created_at: str) -> str:
    start = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    years = now.year - start.year
    months = now.month - start.month
    days = now.day - start.day
    if days < 0:
        months -= 1
        prev_month_end = (now.replace(day=1) - timedelta(days=1)).day
        days += prev_month_end
    if months < 0:
        years -= 1
        months += 12
    return f"{years} years, {months} months, {days} days"


# ── 패널 라인 구성 (세그먼트 = (텍스트, 색상클래스)) ────────
def kv(key: str, value_segments: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """'. key: ····· value' — 값을 우측 정렬하는 점선 리더 라인."""
    value_len = sum(len(t) for t, _ in value_segments)
    dots = PANEL_COLS - len(key) - value_len - 6  # ". " + ": " + 점 양옆 공백
    dots = max(2, dots)
    return [
        (". ", "dim"), (key, "key"), (": ", "dim"),
        ("." * dots, "dim"), (" ", "dim"), *value_segments,
    ]


def section(name: str) -> list[tuple[str, str]]:
    fill = PANEL_COLS - len(name) - 3
    return [("- ", "dim"), (name, "header"), (" ", "dim"), ("─" * fill, "dim")]


def build_panel(stats: dict) -> list[list[tuple[str, str]]]:
    title = "soulduse@github"
    lines: list[list[tuple[str, str]]] = [
        [(title, "title"), (" ", "dim"), ("─" * (PANEL_COLS - len(title) - 1), "dim")],
        [],
        kv("OS", [("macOS, Android, Linux", "val")]),
        kv("Uptime", [(uptime_text(stats["created_at"]), "val")]),
        kv("Host", [("Infinity apps", "val")]),
        kv("Kernel", [("Indie App Factory", "val")]),
        kv("IDE", [("IntelliJ, Android Studio, Claude Code", "val")]),
        [],
        kv("Languages.Programming", [("Kotlin, Python, TypeScript", "val")]),
        kv("Languages.Mobile", [("Android, Flutter, React Native", "val")]),
        kv("Languages.AI", [("LLM Agents, RAG, MCP", "val")]),
        [],
        section("Contact"),
        kv("Blog", [("programmingzombie.com", "val")]),
        kv("Email", [("developerkhy@gmail.com", "val")]),
        [],
        section("GitHub Stats"),
        kv("Repos", [
            (f"{stats['repos_total']:,}", "val"),
            (" {Public: ", "dim"), (f"{stats['repos_public']}", "val"), ("}", "dim"),
            (" | ", "dim"), ("Stars", "key"), (": ", "dim"), (f"{stats['stars']:,}", "val"),
        ]),
        kv("Commits", [
            (f"{stats['commits']:,}", "val"),
            (" | ", "dim"), ("Followers", "key"), (": ", "dim"),
            (f"{stats['followers']:,}", "val"),
        ]),
        kv("Lines of Code", [
            (f"{stats['loc_additions'] - stats['loc_deletions']:,}", "val"),
            (" (", "dim"), (f"{stats['loc_additions']:,}++", "add"),
            (", ", "dim"), (f"{stats['loc_deletions']:,}--", "del"), (")", "dim"),
        ]),
    ]
    return lines


# ── 아트 렌더링 ────────────────────────────────────────────
def tspan(x: float, text: str, fill: str) -> str:
    return (
        f'<tspan x="{x:.1f}" fill="{fill}" '
        f'textLength="{len(text) * ART_CW:.1f}" '
        f'lengthAdjust="spacingAndGlyphs">{escape(text)}</tspan>'
    )


def render_ascii_art(art: dict, theme: str, art_x: float, art_top: float) -> list[str]:
    parts = [f'<g font-family="{FONT_STACK}" font-size="{ASCII_FONT}">']
    for row_idx, runs in enumerate(art["rows"]):
        y = art_top + row_idx * ASCII_LH + ASCII_FONT
        col = 0
        spans = []
        for text, color in runs:
            if color is not None:
                spans.append(tspan(art_x + col * ART_CW, text, adjust_color(color, theme, "ascii")))
            col += len(text)
        if spans:
            parts.append(f'<text y="{y:.1f}">{"".join(spans)}</text>')
    parts.append("</g>")
    return parts


def render_halfblock_art(art: dict, theme: str, art_x: float, art_top: float) -> list[str]:
    """RLE 셀 [count, top, bottom] — top=bottom이면 █ 하나, 아니면 ▀+▄ 겹쳐 그리기."""
    parts = [f'<g font-family="{FONT_STACK}" font-size="{BLOCK_FONT}">']
    for row_idx, runs in enumerate(art["rows"]):
        # 블록 글리프는 em 박스를 채우므로 baseline = 행 상단 + ascent(≈0.8em)
        y = art_top + row_idx * BLOCK_LH + BLOCK_FONT * 0.8
        col = 0
        spans = []
        for count, top, bottom in runs:
            x = art_x + col * ART_CW
            if top and bottom:
                if top == bottom:
                    spans.append(tspan(x, "█" * count, adjust_color(top, theme, "halfblock")))
                else:
                    spans.append(tspan(x, "▀" * count, adjust_color(top, theme, "halfblock")))
                    spans.append(tspan(x, "▄" * count, adjust_color(bottom, theme, "halfblock")))
            elif top:
                spans.append(tspan(x, "▀" * count, adjust_color(top, theme, "halfblock")))
            elif bottom:
                spans.append(tspan(x, "▄" * count, adjust_color(bottom, theme, "halfblock")))
            col += count
        if spans:
            parts.append(f'<text y="{y:.1f}">{"".join(spans)}</text>')
    parts.append("</g>")
    return parts


# ── SVG 조립 ───────────────────────────────────────────────
def render(theme: str, art: dict, stats: dict) -> str:
    colors = THEMES[theme]
    panel = build_panel(stats)
    style = art.get("style", "ascii")
    art_lh = BLOCK_LH if style == "halfblock" else ASCII_LH

    art_w = art["cols"] * ART_CW
    art_h = len(art["rows"]) * art_lh
    panel_w = PANEL_COLS * PANEL_CW
    panel_h = len(panel) * PANEL_LH
    width = int(PAD + art_w + GAP + panel_w + PAD)
    height = int(max(art_h, panel_h) + PAD * 2)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="soulduse — Programming Zombie, GitHub profile card">',
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="8" '
        f'fill="{colors["bg"]}" stroke="{colors["border"]}"/>',
    ]

    art_x = PAD
    art_top = (height - art_h) / 2
    if style == "halfblock":
        parts.extend(render_halfblock_art(art, theme, art_x, art_top))
    else:
        parts.extend(render_ascii_art(art, theme, art_x, art_top))

    panel_x = PAD + art_w + GAP
    panel_y = (height - panel_h) / 2 + PANEL_FONT
    parts.append(f'<g font-family="{FONT_STACK}" font-size="{PANEL_FONT}">')
    for line_idx, segments in enumerate(panel):
        if not segments:
            continue
        y = panel_y + line_idx * PANEL_LH
        col = 0
        spans = []
        for text, cls in segments:
            x = panel_x + col * PANEL_CW
            weight = ' font-weight="bold"' if cls in ("title", "header") else ""
            spans.append(
                f'<tspan x="{x:.1f}" fill="{colors[cls]}"{weight} '
                f'textLength="{len(text) * PANEL_CW:.1f}" '
                f'lengthAdjust="spacingAndGlyphs">{escape(text)}</tspan>'
            )
            col += len(text)
        parts.append(f'<text y="{y:.1f}">{"".join(spans)}</text>')
    parts.append("</g>")

    parts.append("</svg>")
    return "\n".join(parts)


def main() -> None:
    art = json.loads(ART_PATH.read_text())
    stats = json.loads(STATS_PATH.read_text())
    for theme in THEMES:
        out = ROOT / f"profile-{theme}.svg"
        out.write_text(render(theme, art, stats))
        print(f"saved: {out}")


if __name__ == "__main__":
    main()
