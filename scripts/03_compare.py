"""藻場データと、ALBから作った水深・藻場ポテンシャルを比べる。

- 藻場Shapefileを EPSG:6676 に変換し、ALBの範囲で切り抜く
- 藻場の内側と外側で水深の分布を比べ、ヒストグラムを docs/data/depth_hist.png に保存
- 藻場のうち、ポテンシャル域（砂泥タイプ・岩礁タイプ）と重なる面積の割合を計算
- 結果を docs/data/stats.json に保存

使い方: python scripts/03_compare.py
"""
import json
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from rasterio.features import geometry_mask, shapes
from shapely.geometry import box, shape

MOBA_SHP = Path("data/raw/moba/mo2018_utm54/mo2018_utm54.shp")
WORK = Path("data/work")
OUT_DIR = Path("docs/data")
CRS = "EPSG:6676"

MOBA_TYPES = {1: "アマモ場", 2: "海藻藻場", 3: "スガモ場"}
POTENTIAL_TYPES = {1: "砂泥タイプ", 2: "岩礁タイプ"}
DEPTH_BIN_EDGES = np.arange(0, 17, 1)  # 0〜16mを1mごと

# グラフの色（検証済みパレットの1番・2番）と文字の色
COLOR_INSIDE = "#2a78d6"
COLOR_OUTSIDE = "#eb6834"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
SURFACE = "#fcfcfb"


def load_moba(bounds):
    """藻場Shapefileを EPSG:6676 に変換して、ALBの範囲で切り抜く。"""
    area = gpd.GeoSeries([box(*bounds)], crs=CRS)
    # 全国分は大きいので、ALBの範囲の周りだけ読み込む
    moba = gpd.read_file(MOBA_SHP, bbox=tuple(area.to_crs(gpd.read_file(MOBA_SHP, rows=1).crs).total_bounds))
    moba = moba.to_crs(CRS)
    return gpd.clip(moba, area.iloc[0])


def plot_hist(inside, outside, path):
    """藻場の内側・外側の水深分布を、それぞれの面積に対する割合（%）で並べる。"""
    plt.rcParams["font.family"] = ["Yu Gothic", "Meiryo", "MS Gothic", "sans-serif"]
    h_in, _ = np.histogram(inside, bins=DEPTH_BIN_EDGES)
    h_out, _ = np.histogram(outside, bins=DEPTH_BIN_EDGES)
    p_in, p_out = 100 * h_in / h_in.sum(), 100 * h_out / h_out.sum()

    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150, facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    x = DEPTH_BIN_EDGES[:-1] + 0.5
    w = 0.4
    ax.bar(x - w / 2 - 0.01, p_in, width=w, color=COLOR_INSIDE, label=f"藻場の内側（{inside.size:,} m²）")
    ax.bar(x + w / 2 + 0.01, p_out, width=w, color=COLOR_OUTSIDE, label=f"藻場の外側（{outside.size:,} m²）")

    ax.set_xticks(DEPTH_BIN_EDGES)
    ax.set_xlim(0, DEPTH_BIN_EDGES[-1])
    ax.set_xlabel("水深（m）", color=TEXT_SECONDARY)
    ax.set_ylabel("面積の割合（%）", color=TEXT_SECONDARY)
    ax.set_title("藻場の内側と外側の水深の分布（1m ごと）", color=TEXT_PRIMARY, loc="left", fontsize=12)
    ax.grid(axis="y", color="#e4e3df", linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#c9c8c2")
    ax.tick_params(colors=TEXT_SECONDARY)
    ax.legend(frameon=False, labelcolor=TEXT_PRIMARY)
    fig.text(0.01, 0.01, "データ：静岡県 VIRTUAL SHIZUOKA（CC BY 4.0）、環境省 自然環境保全基礎調査 藻場調査 を加工して作成",
             fontsize=7, color=TEXT_SECONDARY)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return p_in, p_out


def depth_summary(values):
    return {
        "面積_m2": int(values.size),
        "平均_m": round(float(values.mean()), 2),
        "中央値_m": round(float(np.median(values)), 2),
        "25%点_m": round(float(np.percentile(values, 25)), 2),
        "75%点_m": round(float(np.percentile(values, 75)), 2),
    }


def main():
    with rasterio.open(WORK / "depth.tif") as src:
        depth = src.read(1, masked=True)
        transform, bounds, pixel_area = src.transform, tuple(src.bounds), abs(src.res[0] * src.res[1])
    with rasterio.open(WORK / "potential.tif") as src:
        potential = src.read(1)

    moba = load_moba(bounds)
    moba["藻場タイプ"] = moba["hanrei_c"].map(MOBA_TYPES)
    moba_area = float(moba.area.sum())
    print(f"ALB範囲内の藻場: {len(moba)} 件、合計 {moba_area:,.1f} m²")

    # 画素の中心が藻場の中にあるかどうか
    in_moba = geometry_mask(moba.geometry, out_shape=depth.shape, transform=transform, invert=True)
    sea = ~depth.mask
    inside = depth.data[sea & in_moba]
    outside = depth.data[sea & ~in_moba]
    p_in, p_out = plot_hist(inside, outside, OUT_DIR / "depth_hist.png")
    print(f"ヒストグラム: {OUT_DIR / 'depth_hist.png'}")
    print(f"水深の中央値: 藻場の内側 {np.median(inside):.2f} m、外側 {np.median(outside):.2f} m")

    # ポテンシャル域を画素の形のまま面にして、藻場と重ねて面積を測る
    pot_polys = [
        {"区分": POTENTIAL_TYPES[int(v)], "geometry": shape(g)}
        for g, v in shapes(potential, mask=np.isin(potential, list(POTENTIAL_TYPES)), transform=transform)
    ]
    pot = gpd.GeoDataFrame(pot_polys, crs=CRS).dissolve(by="区分")
    moba_union = moba.union_all()
    overlap = {name: float(geom.intersection(moba_union).area) for name, geom in pot.geometry.items()}
    overlap_total = sum(overlap.values())
    print(f"藻場のうちポテンシャル域と重なる割合: {overlap_total / moba_area:.1%}")
    for name, a in overlap.items():
        print(f"  {name}: {a:,.1f} m²（{a / moba_area:.1%}）")

    stats = {
        "説明": "ALBの範囲（図郭 08OE2670）で、藻場データと水深・藻場ポテンシャルを比べた結果",
        "座標系": CRS,
        "範囲_m": dict(zip(["xmin", "ymin", "xmax", "ymax"], [round(v, 2) for v in bounds])),
        "画素の大きさ_m": 1,
        "藻場": {
            "件数": len(moba),
            "合計面積_m2": round(moba_area, 1),
            "タイプ別面積_m2": {k: round(float(v), 1) for k, v in moba.groupby("藻場タイプ").geometry.apply(lambda s: s.area.sum()).items()},
            "判読に使った衛星画像": sorted(moba["satellite"].dropna().unique().tolist()),
        },
        "水深": {
            "藻場の内側": depth_summary(inside),
            "藻場の外側": depth_summary(outside),
            "ヒストグラム": {
                "区間_m": [f"{a}-{b}" for a, b in zip(DEPTH_BIN_EDGES[:-1], DEPTH_BIN_EDGES[1:])],
                "藻場の内側_割合%": [round(float(v), 2) for v in p_in],
                "藻場の外側_割合%": [round(float(v), 2) for v in p_out],
            },
        },
        "藻場とポテンシャル域の重なり": {
            "重なる面積_m2": {k: round(v, 1) for k, v in overlap.items()},
            "重なる面積の合計_m2": round(overlap_total, 1),
            "藻場面積に対する割合": round(overlap_total / moba_area, 4),
            "区分別の割合": {k: round(v / moba_area, 4) for k, v in overlap.items()},
        },
        "出典": [
            "静岡県「VIRTUAL SHIZUOKA 静岡県 伊豆西部 点群データ」ALBデータ 図郭 08OE2670、G空間情報センター "
            "https://www.geospatial.jp/ckan/dataset/shizuoka-2020-pointcloud （CC BY 4.0）を加工して作成",
            "環境省自然環境局 生物多様性センター「自然環境保全基礎調査 藻場調査2018-2020（UTM54）」、環境ジオポータル "
            "https://geoportal.env.go.jp/datasets/1209759c6d614dacad11f48b9e113032_0/about "
            "（政府標準利用規約 第2.0版）を加工して作成",
        ],
        "ライセンス": "CC BY 4.0",
    }
    with open(OUT_DIR / "stats.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"結果: {OUT_DIR / 'stats.json'}")


if __name__ == "__main__":
    main()
