"""ALBデータから1m間隔の地形（DEM）のGeoTIFFを作る。

- data/raw/alb/ にグリッドデータ（*_DEM.txt、zipの中でも可）があれば、それを使う
- なければ、LAS点群のうち地面・海底の点から作る
- 座標系は EPSG:6676（JGD2011 平面直角座標系 第Ⅷ系）

使い方:
    python scripts/01_make_dem.py            # グリッドデータを優先
    python scripts/01_make_dem.py --las      # LAS点群から作る（確認用）
"""
import argparse
import io
import zipfile
from pathlib import Path

import laspy
import numpy as np
import rasterio
from rasterio.transform import from_origin

RAW_DIR = Path("data/raw/alb")
LAS_PATH = Path("data/work/alb/08OE2670.las")
OUT_PATH = Path("data/work/dem.tif")
CRS = "EPSG:6676"
CELL = 1.0  # 格子の大きさ（m）
NODATA = -9999.0

# 地面・海底とみなす分類コード
# 2 = 地面（陸）。12・22 は独自コードで、グリッドデータの高さとほぼ一致したので海底と判断（推定）
# 11 はグリッドより数m高い位置にあり、水面・水中の点と考えられるので使わない
GROUND_CLASSES = [2, 12, 22]


def find_grid_text():
    """data/raw/alb/ からグリッドデータを探し、テキストとして返す（なければ None）。"""
    for txt in sorted(RAW_DIR.glob("*_DEM.txt")):
        return txt.name, txt.read_text()
    for zp in sorted(RAW_DIR.glob("*.zip")):
        with zipfile.ZipFile(zp) as z:
            for name in z.namelist():
                if name.endswith("_DEM.txt"):
                    return name, z.read(name).decode("ascii")
    return None


def points_to_grid(x, y, z, bounds):
    """点（x, y, z）を1mの格子に入れ、格子ごとの平均の高さを返す。"""
    xmin, ymin, xmax, ymax = bounds
    ncol = int(round((xmax - xmin) / CELL))
    nrow = int(round((ymax - ymin) / CELL))
    col = np.floor((x - xmin) / CELL).astype(int)
    row = np.floor((ymax - y) / CELL).astype(int)  # 画像は上（北）から下へ並ぶ
    ok = (col >= 0) & (col < ncol) & (row >= 0) & (row < nrow)
    idx = row[ok] * ncol + col[ok]
    total = np.bincount(idx, weights=z[ok], minlength=nrow * ncol)
    count = np.bincount(idx, minlength=nrow * ncol)
    dem = np.full(nrow * ncol, NODATA, dtype="float32")
    dem[count > 0] = total[count > 0] / count[count > 0]
    return dem.reshape(nrow, ncol)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--las", action="store_true", help="グリッドデータを使わずLASから作る")
    args = parser.parse_args()

    las_header = laspy.open(LAS_PATH).header
    # 格子の範囲：LASの範囲を1m単位に合わせる
    bounds = (
        np.floor(las_header.mins[0]), np.floor(las_header.mins[1]),
        np.ceil(las_header.maxs[0]), np.ceil(las_header.maxs[1]),
    )

    grid = None if args.las else find_grid_text()
    if grid:
        name, text = grid
        print(f"グリッドデータを使います: {name}")
        g = np.loadtxt(io.StringIO(text))
        # 0.5m間隔の格子点を、1mの格子ごとに平均する
        dem = points_to_grid(g[:, 0], g[:, 1], g[:, 2], bounds)
        source = f"グリッドデータ {name}（0.5m間隔を1mに平均）"
    else:
        print(f"LAS点群を使います: {LAS_PATH}（分類コード {GROUND_CLASSES}）")
        las = laspy.read(LAS_PATH)
        keep = np.isin(np.asarray(las.classification), GROUND_CLASSES)
        dem = points_to_grid(np.asarray(las.x)[keep], np.asarray(las.y)[keep], np.asarray(las.z)[keep], bounds)
        source = f"LAS点群 {LAS_PATH.name} の分類コード {GROUND_CLASSES}"

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        OUT_PATH, "w", driver="GTiff", width=dem.shape[1], height=dem.shape[0], count=1,
        dtype="float32", crs=CRS, transform=from_origin(bounds[0], bounds[3], CELL, CELL),
        nodata=NODATA, compress="deflate",
    ) as dst:
        dst.write(dem, 1)
        dst.update_tags(SOURCE=source)

    valid = dem[dem != NODATA]
    print(f"出力: {OUT_PATH}（{dem.shape[1]} × {dem.shape[0]} 画素、{CELL:g}m間隔、{CRS}）")
    print(f"範囲: X {bounds[0]:.0f}〜{bounds[2]:.0f}、Y {bounds[1]:.0f}〜{bounds[3]:.0f}")
    print(f"最小標高: {valid.min():.2f} m")
    print(f"最大標高: {valid.max():.2f} m")
    print(f"データのない画素: {dem.size - valid.size:,} / {dem.size:,}（{(dem.size - valid.size) / dem.size:.2%}）")


if __name__ == "__main__":
    main()
