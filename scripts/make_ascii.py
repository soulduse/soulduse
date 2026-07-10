"""avatar.png(픽셀아트)을 컬러 ASCII 아트(JSON)로 변환한다.

한 번만 실행하면 되는 스크립트. 결과는 ascii_art.json에 저장되고
generate_svg.py가 이를 읽어 SVG 텍스트로 렌더링한다.

JSON 구조: {"cols": int, "rows": [[[text, "#rrggbb"], ...], ...]}
  - 각 row는 (연속 문자열, 색상) 런(run)의 리스트. 공백 런은 색상 null.
"""
import json
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


def luminance(rgb: tuple[int, int, int]) -> float:
    r, g, b = rgb
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def is_background(rgb: tuple[int, int, int], bg: tuple[int, int, int]) -> bool:
    return all(abs(c - b) <= BG_TOLERANCE for c, b in zip(rgb, bg))


def main() -> None:
    img = Image.open(SRC).convert("RGB")
    w, h = img.size
    px = img.load()
    bg = px[0, 0]

    rows: list[list[list]] = []
    for gy in range(ROWS):
        # 셀 영역 평균(배경 픽셀 제외)으로 색/밝기 결정
        y0, y1 = int(gy * h / ROWS), int((gy + 1) * h / ROWS)
        runs: list[list] = []
        cur_text, cur_color = "", None
        for gx in range(COLS):
            x0, x1 = int(gx * w / COLS), int((gx + 1) * w / COLS)
            rs = gs = bs = n = total = 0
            for y in range(y0, max(y0 + 1, y1)):
                for x in range(x0, max(x0 + 1, x1)):
                    total += 1
                    p = px[x, y]
                    if is_background(p, bg):
                        continue
                    rs += p[0]
                    gs += p[1]
                    bs += p[2]
                    n += 1
            if n == 0 or n / total < 0.35:  # 셀 대부분이 배경이면 공백
                ch, color = " ", None
            else:
                avg = (rs // n, gs // n, bs // n)
                # 감마 0.55: 어두운 부위(선글라스·정장)도 중간 밀도 문자로 형태 유지
                lum = (luminance(avg) / 255) ** 0.55
                idx = min(len(RAMP) - 1, max(2, round(lum * (len(RAMP) - 1))))
                ch = RAMP[idx]
                color = "#{:02x}{:02x}{:02x}".format(*avg)
            if color == cur_color:
                cur_text += ch
            else:
                if cur_text:
                    runs.append([cur_text, cur_color])
                cur_text, cur_color = ch, color
        if cur_text:
            runs.append([cur_text, cur_color])
        rows.append(runs)

    OUT.write_text(json.dumps({"cols": COLS, "rows": rows}, ensure_ascii=False))
    # 터미널 미리보기
    for runs in rows:
        print("".join(text for text, _ in runs))
    print(f"\nsaved: {OUT}")


if __name__ == "__main__":
    main()
