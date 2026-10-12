"""dem.tif から水深・傾斜・ざらつきを計算し、藻場ポテンシャル区分図を作る。

出力（すべて data/work/）:
    depth.tif      水深（m）。標高0m未満を海域とし、水深 = -標高。陸はデータなし
    slope.tif      傾斜（度）
    rugosity.tif   ざらつき（周囲3×3画素の標高の標準偏差、m）
    potential.tif  藻場ポテンシャル区分（1=砂泥タイプ、2=岩礁タイプ、0=海域だが対象外、255=陸・データなし）

使い方: python scripts/02_analyze.py
"""
from pathlib import Path

import numpy as np
import rasterio
from numpy.lib.stride_tricks import sliding_window_view

WORK = Path("data/work")
NODATA = -9999.0

# 手順書の簡易ルール
SAND_DEPTH = (1, 10)   # 砂泥タイプ：水深1〜10m
SAND_MAX_SLOPE = 5     # 砂泥タイプ：傾斜5°未満
ROCK_DEPTH = (1, 15)   # 岩礁タイプ：水深1〜15m

DEPTH_BINS = [(0, 2), (2, 5), (5, 10), (10, 15), (15, np.inf)]


def save(name, array, profile, dtype="float32", nodata=NODATA):
    p = profile.copy()
    p.update(dtype=dtype, nodata=nodata, count=1, compress="deflate")
    with rasterio.open(WORK / name, "w", **p) as dst:
        dst.write(array.astype(dtype), 1)


def main():
    with rasterio.open(WORK / "dem.tif") as src:
        dem = src.read(1, masked=True).filled(np.nan).astype("float64")
        profile = src.profile
        cell = src.res[0]
        pixel_area = src.res[0] * src.res[1]

    has_data = ~np.isnan(dem)
    sea = has_data & (dem < 0)

    # 水深：海域だけ。陸はデータなし
    depth = np.where(sea, -dem, np.nan)

    # 傾斜：となりの画素との高さの差から計算（度）
    dz_dy, dz_dx = np.gradient(dem, cell)
    slope = np.degrees(np.arctan(np.hypot(dz_dx, dz_dy)))

    # ざらつき：周囲3×3画素の標高の標準偏差。端やデータなしを含む場所は計算しない
    rug = np.full(dem.shape, np.nan)
    rug[1:-1, 1:-1] = sliding_window_view(dem, (3, 3)).std(axis=(-1, -2))

    # ざらつきの「大・小」の境目 = 海域のざらつきの中央値
    rug_threshold = float(np.nanmedian(rug[sea]))

    d, r = (np.nan_to_num(a, nan=-1) for a in (depth, rug))
    rug_ok = r >= 0
    sand = sea & (d >= SAND_DEPTH[0]) & (d <= SAND_DEPTH[1]) & (slope < SAND_MAX_SLOPE) & rug_ok & (r < rug_threshold)
    rock = sea & (d >= ROCK_DEPTH[0]) & (d <= ROCK_DEPTH[1]) & rug_ok & (r >= rug_threshold)

    potential = np.full(dem.shape, 255, dtype="uint8")
    potential[sea] = 0
    potential[sand] = 1
    potential[rock] = 2

    save("depth.tif", np.nan_to_num(depth, nan=NODATA), profile)
    save("slope.tif", np.nan_to_num(slope, nan=NODATA), profile)
    save("rugosity.tif", np.nan_to_num(rug, nan=NODATA), profile)
    save("potential.tif", potential, profile, dtype="uint8", nodata=255)

    print("出力: depth.tif, slope.tif, rugosity.tif, potential.tif（data/work/）")
    print(f"\nざらつきの境目（海域の中央値）: {rug_threshold:.4f} m")
    print(f"水深: {np.nanmin(depth):.2f}〜{np.nanmax(depth):.2f} m")
    print(f"傾斜（海域）: 中央値 {np.nanmedian(slope[sea]):.1f}°、最大 {np.nanmax(slope[sea]):.1f}°")

    print("\n## 水深の区分ごとの面積")
    print("| 水深 | 面積（m²） | 割合 |")
    print("|---|---:|---:|")
    total = dem.size * pixel_area
    rows = []
    for lo, hi in DEPTH_BINS:
        n = np.count_nonzero(sea & (depth >= lo) & (depth < hi))
        label = f"{lo}m以上" if np.isinf(hi) else f"{lo}–{hi}m"
        rows.append((label, n * pixel_area))
    rows.append(("データなし", np.count_nonzero(~has_data) * pixel_area))
    rows.append(("（陸：標高0m以上）", np.count_nonzero(has_data & ~sea) * pixel_area))
    for label, area in rows:
        print(f"| {label} | {area:,.0f} | {area / total:.1%} |")
    print(f"| 合計 | {total:,.0f} | 100.0% |")

    print("\n## 藻場ポテンシャル区分の面積")
    print("| 区分 | 面積（m²） | 海域に占める割合 |")
    print("|---|---:|---:|")
    sea_area = np.count_nonzero(sea) * pixel_area
    for code, label in [(1, "砂泥タイプ"), (2, "岩礁タイプ"), (0, "海域だが対象外")]:
        area = np.count_nonzero(potential == code) * pixel_area
        print(f"| {label} | {area:,.0f} | {area / sea_area:.1%} |")
    print(f"| 海域の合計 | {sea_area:,.0f} | 100.0% |")


if __name__ == "__main__":
    main()
