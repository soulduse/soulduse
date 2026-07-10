"""avatar.png(픽셀아트)을 터미널 아트(JSON)로 변환한다.

두 가지 스타일 지원:
  python3 make_ascii.py ascii      # 문자 밀도 램프 ASCII 아트
  python3 make_ascii.py halfblock  # ▀▄█ 하프블록 모자이크 (세로 해상도 2배, 기본값)

셀 색상은 평균이 아닌 지배색(dominant color)을 쓴다 — 픽셀아트의 플랫한
팔레트가 외곽선과 섞여 탁해지는 것을 막는다. 결과는 ascii_art.json에 저장되고
generate_svg.py가 style 필드를 보고 렌더링 방식을 분기한다.

JSON 구조:
  ascii:     {"style": "ascii", "cols": N, "rows": [[[text, "#rrggbb"], ...], ...]}
  halfblock: {"style": "halfblock", "cols": N,
              "rows": [[[count, top|null, bottom|null], ...], ...]}  # RLE
"""
import colorsys
import json
import sys
from collections import Counter
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "avatar.png"
OUT = ROOT / "ascii_art.json"

COLS = 64
ROWS = 32  # 정사각 유지: cols × (문자폭 6.6 / 행높이 13) ≈ 32

# 어두운 픽셀 → 성긴 문자, 밝은 픽셀 → 촘촘한 문자 (다크 배경 기준)
RAMP = " .':;+=xX$&@"
BG_TOLERANCE = 28  # 배경색(모서리 픽셀)과의 채널당 허용 오차
SATURATION_BOOST = 1.25


def luminance(rgb: tuple[int, int, int]) -> float:
    r, g, b = rgb
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def is_background(rgb: tuple[int, int, int], bg: tuple[int, int, int]) -> bool:
    return all(abs(c - b) <= BG_TOLERANCE for c, b in zip(rgb, bg))


def boost(rgb: tuple[int, int, int]) -> str:
    """채도를 살짝 올려 픽셀아트 특유의 쨍한 색을 유지한다."""
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
    r, g, b = colorsys.hsv_to_rgb(h, min(1.0, s * SATURATION_BOOST), v)
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


def dominant_color(px, bg, x0: int, x1: int, y0: int, y1: int) -> str | None:
    """영역의 지배색. 대부분 배경이면 None. 색은 16단계로 양자화해 카운트."""
    counter: Counter = Counter()
    total = 0
    for y in range(y0, max(y0 + 1, y1)):
        for x in range(x0, max(x0 + 1, x1)):
            total += 1
            p = px[x, y]
            if is_background(p, bg):
                continue
            counter[(p[0] // 16, p[1] // 16, p[2] // 16)] += 1
    if not counter or sum(counter.values()) / total < 0.5:
        return None
    # 단순 다수결이면 포인트 컬러(청록 눈, 금 하이라이트)가 검정 테두리에 먹힌다 —
    # 채도·명도가 높은 색에 가중치를 줘 셀의 '눈에 띄는' 색을 지배색으로 채택
    best_q, best_score = None, -1.0
    for q, count in counter.items():
        rgb = (q[0] * 16 + 8, q[1] * 16 + 8, q[2] * 16 + 8)
        _, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
        score = count * (0.4 + s + 0.6 * v)
        if score > best_score:
            best_q, best_score = q, score
    return boost((best_q[0] * 16 + 8, best_q[1] * 16 + 8, best_q[2] * 16 + 8))


def make_ascii(px, bg, w: int, h: int) -> dict:
    rows = []
    for gy in range(ROWS):
        y0, y1 = int(gy * h / ROWS), int((gy + 1) * h / ROWS)
        runs: list[list] = []
        cur_text, cur_color = "", None
        for gx in range(COLS):
            x0, x1 = int(gx * w / COLS), int((gx + 1) * w / COLS)
            color = dominant_color(px, bg, x0, x1, y0, y1)
            if color is None:
                ch = " "
            else:
                rgb = tuple(int(color[i : i + 2], 16) for i in (1, 3, 5))
                # 감마 0.55: 어두운 부위(선글라스·정장)도 중간 밀도 문자로 형태 유지
                lum = (luminance(rgb) / 255) ** 0.55
                ch = RAMP[min(len(RAMP) - 1, max(2, round(lum * (len(RAMP) - 1))))]
            if color == cur_color:
                cur_text += ch
            else:
                if cur_text:
                    runs.append([cur_text, cur_color])
                cur_text, cur_color = ch, color
        if cur_text:
            runs.append([cur_text, cur_color])
        rows.append(runs)
    return {"style": "ascii", "cols": COLS, "rows": rows}


def make_halfblock(px, bg, w: int, h: int) -> dict:
    """셀 하나에 상/하 두 서브픽셀(▀▄) — 세로 64 서브행으로 원본에 근접."""
    sub_rows = ROWS * 2
    rows = []
    for gy in range(ROWS):
        cells = []
        for gx in range(COLS):
            x0, x1 = int(gx * w / COLS), int((gx + 1) * w / COLS)
            ty0, ty1 = int(gy * 2 * h / sub_rows), int((gy * 2 + 1) * h / sub_rows)
            by0, by1 = ty1, int((gy * 2 + 2) * h / sub_rows)
            cells.append((
                dominant_color(px, bg, x0, x1, ty0, ty1),
                dominant_color(px, bg, x0, x1, by0, by1),
            ))
        runs: list[list] = []
        for top, bottom in cells:  # 동일 (top, bottom) 연속 셀을 RLE로 압축
            if runs and runs[-1][1] == top and runs[-1][2] == bottom:
                runs[-1][0] += 1
            else:
                runs.append([1, top, bottom])
        rows.append(runs)
    return {"style": "halfblock", "cols": COLS, "rows": rows}


def main() -> None:
    style = sys.argv[1] if len(sys.argv) > 1 else "halfblock"
    src = Image.open(SRC).convert("RGB")
    # 소수 팔레트로 양자화 — AI 생성 픽셀아트의 미세 노이즈/그라데이션을 정리해
    # 플랫 영역은 플랫하게 만든다. 단, 희귀 포인트 컬러(청록 눈 등)는 양자화가
    # 회색으로 뭉개므로, 고채도 픽셀은 원본색을 그대로 유지한다.
    img = src.quantize(colors=32, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).convert("RGB")
    spx, px = src.load(), img.load()
    for y in range(img.height):
        for x in range(img.width):
            h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in spx[x, y]))
            if s > 0.55 and v > 0.5:
                px[x, y] = spx[x, y]
    bg = px[0, 0]

    build = make_halfblock if style == "halfblock" else make_ascii
    art = build(px, bg, *img.size)
    OUT.write_text(json.dumps(art, ensure_ascii=False))

    for runs in art["rows"]:  # 터미널 미리보기
        if style == "halfblock":
            line = "".join(
                ("█" if t and b else "▀" if t else "▄" if b else " ") * n
                for n, t, b in runs
            )
        else:
            line = "".join(text for text, _ in runs)
        print(line)
    print(f"\nsaved: {OUT} (style={style})")


if __name__ == "__main__":
    main()
