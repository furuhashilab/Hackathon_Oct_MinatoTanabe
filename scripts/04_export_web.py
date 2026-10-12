"""Webマップ（MapLibre GL JS）用のデータを docs/data/ に書き出す。

出力（docs/data/）:
    depth.png          水深図（EPSG:3857 に変換して色付けした透過PNG）
    potential.png      藻場ポテンシャル図（同上）
    bounds.json        2つのPNGの四隅の緯度経度と凡例
    contours.geojson   5m間隔の等深線（WGS84）
    moba.geojson       ALBの範囲で切り抜いた藻場（WGS84）
    profile_line.geojson  断面線（WGS84）
    profile.json       断面線に沿った標高・水深
    points.json        3D表示用に間引いた点群（経度・緯度・標高・分類コード）

使い方: python scripts/04_export_web.py
"""
import json
from pathlib import Path

import geopandas as gpd
import laspy
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from matplotlib.colors import LinearSegmentedColormap
from PIL import Image
from pyproj import Transformer
from rasterio.features import geometry_mask
from rasterio.warp import Resampling, calculate_default_transform, reproject
from shapely.geometry import LineString, box

WORK = Path("data/work")
OUT = Path("docs/data")
LAS_PATH = WORK / "alb/08OE2670.las"
MOBA_SHP = Path("data/raw/moba/mo2018_utm54/mo2018_utm54.shp")
SRC_CRS = "EPSG:6676"
WEB_CRS = "EPSG:3857"
MAX_TOTAL_MB = 50

# 断面線：南の海岸（陸）から、いちばん深い北西の角へ。藻場の上を通る
PROFILE_START = (24250.0, -128330.0)
PROFILE_END = (24000.0, -128100.0)
PROFILE_STEP = 1.0  # m

CONTOUR_LEVELS = [0, 5, 10, 15]  # 水深（m）。0m は海岸線
MAX_POINTS = 200_000
POINT_CLASSES = [1, 2, 12, 22]  # 11（水面・水中の点らしい）は除く

# 色：水深は青の濃淡（浅い=淡い、深い=濃い）。区分はパレットの1番・2番
DEPTH_RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]
DEPTH_MAX = 16.0
NO_DATA_COLOR = (128, 128, 128, 255)          # データなし：灰色
POTENTIAL_COLORS = {
    1: ("砂泥タイプ", "#2a78d6"),
    2: ("岩礁タイプ", "#eb6834"),
    0: ("海域だが対象外", "#c9c8c2"),
}
OUTSIDE_ALPHA = 0.45  # 「対象外」は薄く表示する

MOBA_TYPES = {1: "アマモ場", 2: "海藻藻場", 3: "スガモ場"}

to_wgs84 = Transformer.from_crs(SRC_CRS, "EPSG:4326", always_xy=True)


def hex_rgba(h, alpha=1.0):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (int(round(alpha * 255)),)


def write_geojson(gdf, path, precision=6):
    gdf.to_crs("EPSG:4326").to_file(path, driver="GeoJSON", COORDINATE_PRECISION=precision)


def warp_to_web(arr, src_transform, src_crs, resampling, scale):
    """EPSG:3857 に変換する。scale を大きくすると画素が粗くなる。"""
    h, w = arr.shape
    left, top = src_transform.c, src_transform.f
    bounds = (left, top + src_transform.e * h, left + src_transform.a * w, top)
    dst_transform, dw, dh = calculate_default_transform(src_crs, WEB_CRS, w, h, *bounds)
    dst_transform = dst_transform * dst_transform.scale(scale)
    dw, dh = int(np.ceil(dw / scale)), int(np.ceil(dh / scale))
    dst = np.full((dh, dw), np.nan, dtype="float32")
    reproject(arr.astype("float32"), dst, src_transform=src_transform, src_crs=src_crs,
              dst_transform=dst_transform, dst_crs=WEB_CRS, src_nodata=np.nan, dst_nodata=np.nan,
              resampling=resampling)
    return dst, dst_transform


def corners_lonlat(transform, shape):
    """PNGの四隅（左上・右上・右下・左下）の経度緯度。MapLibre の image ソースの順番。"""
    h, w = shape
    to_ll = Transformer.from_crs(WEB_CRS, "EPSG:4326", always_xy=True)
    pts = [transform * (0, 0), transform * (w, 0), transform * (w, h), transform * (0, h)]
    return [[round(v, 7) for v in to_ll.transform(x, y)] for x, y in pts]


def export_rasters(scale):
    with rasterio.open(WORK / "dem.tif") as src:
        dem = src.read(1, masked=True).filled(np.nan)
        transform = src.transform
    with rasterio.open(WORK / "potential.tif") as src:
        potential = src.read(1).astype("float32")
    # 陸（標高0m以上）は透明、DEMのデータなしは灰色にするため、DEMも一緒に変換する
    potential[np.isnan(dem) | (dem >= 0)] = np.nan

    dem_w, web_transform = warp_to_web(dem, transform, SRC_CRS, Resampling.bilinear, scale)
    pot_w, _ = warp_to_web(potential, transform, SRC_CRS, Resampling.nearest, scale)
    # 変換前の範囲の内側かどうか（外側の三角形の部分は透明にする）
    inside_w, _ = warp_to_web(np.ones_like(dem), transform, SRC_CRS, Resampling.nearest, scale)
    inside = ~np.isnan(inside_w)
    no_data = inside & np.isnan(dem_w)
    sea = inside & (dem_w < 0)

    # 水深図
    cmap = LinearSegmentedColormap.from_list("depth", DEPTH_RAMP)
    rgba = np.zeros(dem_w.shape + (4,), dtype="uint8")
    depth = np.clip(-dem_w, 0, DEPTH_MAX) / DEPTH_MAX
    rgba[sea] = (cmap(depth[sea]) * 255).astype("uint8")
    rgba[no_data] = NO_DATA_COLOR
    Image.fromarray(rgba, "RGBA").save(OUT / "depth.png", optimize=True)

    # 藻場ポテンシャル図
    rgba = np.zeros(dem_w.shape + (4,), dtype="uint8")
    for code, (_, color) in POTENTIAL_COLORS.items():
        rgba[sea & (pot_w == code)] = hex_rgba(color, OUTSIDE_ALPHA if code == 0 else 1.0)
    rgba[no_data] = NO_DATA_COLOR
    Image.fromarray(rgba, "RGBA").save(OUT / "potential.png", optimize=True)

    res = abs(web_transform.a)
    return {
        "説明": "depth.png と potential.png の四隅の経度緯度（左上・右上・右下・左下）。MapLibre の image ソースの coordinates にそのまま使える",
        "coordinates": corners_lonlat(web_transform, dem_w.shape),
        "画素数": {"幅": dem_w.shape[1], "高さ": dem_w.shape[0]},
        "画素の大きさ_EPSG3857_m": round(res, 3),
        "凡例": {
            "depth.png": {
                "種類": "水深（m）",
                "範囲_m": [0, DEPTH_MAX],
                "色": DEPTH_RAMP,
                "データなし": "灰色 #808080",
                "陸": "透明",
            },
            "potential.png": {
                **{label: color for label, color in POTENTIAL_COLORS.values()},
                "データなし": "#808080",
                "陸": "透明",
            },
        },
    }


def export_contours():
    with rasterio.open(WORK / "dem.tif") as src:
        dem = src.read(1, masked=True)
        transform = src.transform
    h, w = dem.shape
    xs = transform.c + transform.a * (np.arange(w) + 0.5)
    ys = transform.f + transform.e * (np.arange(h) + 0.5)
    fig, ax = plt.subplots()
    cs = ax.contour(xs, ys, -dem, levels=CONTOUR_LEVELS)
    rows = []
    for level, segs in zip(cs.levels, cs.allsegs):
        for seg in segs:
            if len(seg) >= 2:
                rows.append({"水深_m": int(level), "geometry": LineString(seg)})
    plt.close(fig)
    gdf = gpd.GeoDataFrame(rows, crs=SRC_CRS)
    gdf["geometry"] = gdf.simplify(0.25)
    write_geojson(gdf, OUT / "contours.geojson")
    return len(gdf)


def export_moba(bounds):
    area = gpd.GeoSeries([box(*bounds)], crs=SRC_CRS)
    shp_crs = gpd.read_file(MOBA_SHP, rows=1).crs
    moba = gpd.read_file(MOBA_SHP, bbox=tuple(area.to_crs(shp_crs).total_bounds)).to_crs(SRC_CRS)
    moba = gpd.clip(moba, area.iloc[0])
    moba = moba.assign(
        藻場タイプ=moba["hanrei_c"].map(MOBA_TYPES),
        面積_m2=moba.area.round(1),
        衛星画像=moba["satellite"],
    )[["objectid", "hanrei_c", "藻場タイプ", "面積_m2", "衛星画像", "geometry"]]
    write_geojson(moba, OUT / "moba.geojson")
    return moba


def export_profile(moba):
    with rasterio.open(WORK / "dem.tif") as src:
        dem = src.read(1, masked=True).filled(np.nan)
        transform = src.transform
    with rasterio.open(WORK / "potential.tif") as src:
        potential = src.read(1)
    in_moba = geometry_mask(moba.geometry, out_shape=dem.shape, transform=transform, invert=True)

    line = LineString([PROFILE_START, PROFILE_END])
    n = int(line.length // PROFILE_STEP) + 1
    labels = {code: label for code, (label, _) in POTENTIAL_COLORS.items()}
    samples = []
    for i in range(n):
        p = line.interpolate(i * PROFILE_STEP)
        col, row = ~transform * (p.x, p.y)
        r, c = int(row), int(col)
        z = float(dem[r, c])
        lon, lat = to_wgs84.transform(p.x, p.y)
        samples.append({
            "距離_m": round(i * PROFILE_STEP, 1),
            "経度": round(lon, 7),
            "緯度": round(lat, 7),
            "標高_m": None if np.isnan(z) else round(z, 2),
            "水深_m": None if np.isnan(z) or z >= 0 else round(-z, 2),
            "藻場": bool(in_moba[r, c]),
            "ポテンシャル": labels.get(int(potential[r, c])),
        })
    profile = {
        "説明": "南の海岸（陸）から北西の沖へ向かう断面。距離は始点（陸側）から",
        "始点_EPSG6676": PROFILE_START,
        "終点_EPSG6676": PROFILE_END,
        "間隔_m": PROFILE_STEP,
        "points": samples,
    }
    with open(OUT / "profile.json", "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, separators=(",", ":"))
    write_geojson(gpd.GeoDataFrame([{"名前": "断面線", "長さ_m": round(line.length, 1), "geometry": line}], crs=SRC_CRS),
                  OUT / "profile_line.geojson")
    return samples


def export_points(max_points):
    las = laspy.read(LAS_PATH)
    cls = np.asarray(las.classification)
    idx = np.flatnonzero(np.isin(cls, POINT_CLASSES))
    rng = np.random.default_rng(0)  # 毎回同じ点が選ばれるよう乱数を固定
    if idx.size > max_points:
        idx = np.sort(rng.choice(idx, max_points, replace=False))
    lon, lat = to_wgs84.transform(np.asarray(las.x)[idx], np.asarray(las.y)[idx])
    z = np.asarray(las.z)[idx]
    data = {
        "説明": f"ALB点群から分類コード {POINT_CLASSES} の点を {idx.size:,} 点に間引いたもの（標高は m）",
        "columns": ["経度", "緯度", "標高_m", "分類コード"],
        "points": [[round(float(a), 7), round(float(b), 7), round(float(c), 2), int(d)]
                   for a, b, c, d in zip(lon, lat, z, cls[idx])],
    }
    with open(OUT / "points.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    return idx.size


def total_mb():
    return sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file()) / 1024 / 1024


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with rasterio.open(WORK / "dem.tif") as src:
        bounds = tuple(src.bounds)

    n_contours = export_contours()
    moba = export_moba(bounds)
    samples = export_profile(moba)

    # 50MBを超えたら、PNGの画素を粗くし、点の数も減らしてやり直す
    scale, max_points = 1, MAX_POINTS
    while True:
        meta = export_rasters(scale)
        n_points = export_points(max_points)
        size = total_mb()
        if size <= MAX_TOTAL_MB or scale >= 8:
            break
        print(f"docs/data/ が {size:.1f} MB なので、解像度を下げてやり直します")
        scale, max_points = scale * 2, max_points // 2
    with open(OUT / "bounds.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    depths = [s["水深_m"] for s in samples if s["水深_m"] is not None]
    print(f"PNG: {meta['画素数']['幅']} × {meta['画素数']['高さ']} 画素（{meta['画素の大きさ_EPSG3857_m']} m/画素、EPSG:3857）")
    print(f"四隅（左上・右上・右下・左下）: {meta['coordinates']}")
    print(f"等深線: {n_contours} 本（水深 {CONTOUR_LEVELS} m）")
    print(f"藻場: {len(moba)} 件")
    print(f"断面: {len(samples)} 点、最大水深 {max(depths):.2f} m、藻場の上 {sum(s['藻場'] for s in samples)} m")
    print(f"点群: {n_points:,} 点")
    print("\n## docs/data/ のファイル")
    for p in sorted(OUT.rglob("*")):
        if p.is_file():
            print(f"  {p.name:22s} {p.stat().st_size / 1024:9.1f} KB")
    print(f"合計: {total_mb():.2f} MB（上限 {MAX_TOTAL_MB} MB）")


if __name__ == "__main__":
    main()
