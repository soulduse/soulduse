"""ascii_art.json + stats.json → profile-dark.svg / profile-light.svg 생성.

neofetch 스타일 카드: 좌측 컬러 ASCII 아바타, 우측 시스템 정보 패널.
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
ART_FONT, ART_CW, ART_LH = 11, 6.6, 13.0
PANEL_FONT, PANEL_CW, PANEL_LH = 13, 7.8, 20.0
PANEL_COLS = 58
GAP = 34  # ASCII ↔ 패널 간격

FONT_STACK = "'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace"

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


def adjust_color(hex_color: str, theme: str) -> str:
    """ASCII 아트 색상을 테마 배경에서 보이도록 보정."""
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    if theme == "dark":  # 다크 배경: 전체 밝기 부스트 + 극암부 바닥값
        scale = max(1.35, min(2.4, 65 / max(lum, 1)))
        r, g, b = (min(255, int(c * scale)) for c in (r, g, b))
    else:  # 흰 배경: 밝은 색일수록 강하게 다크닝(암부는 거의 유지)
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


# ── SVG 렌더링 ─────────────────────────────────────────────
def render(theme: str, art: dict, stats: dict) -> str:
    colors = THEMES[theme]
    panel = build_panel(stats)

    art_w = art["cols"] * ART_CW
    art_h = len(art["rows"]) * ART_LH
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

    # 좌측 ASCII 아트 (세로 중앙 정렬)
    art_x = PAD
    art_y = (height - art_h) / 2 + ART_FONT
    parts.append(f'<g font-family="{FONT_STACK}" font-size="{ART_FONT}">')
    for row_idx, runs in enumerate(art["rows"]):
        y = art_y + row_idx * ART_LH
        col = 0
        spans = []
        for text, color in runs:
            if color is not None:
                x = art_x + col * ART_CW
                spans.append(
                    f'<tspan x="{x:.1f}" fill="{adjust_color(color, theme)}" '
                    f'textLength="{len(text) * ART_CW:.1f}" '
                    f'lengthAdjust="spacingAndGlyphs">{escape(text)}</tspan>'
                )
            col += len(text)
        if spans:
            parts.append(f'<text y="{y:.1f}">{"".join(spans)}</text>')
    parts.append("</g>")

    # 우측 정보 패널 (세로 중앙 정렬)
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
