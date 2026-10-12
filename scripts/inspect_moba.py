"""藻場Shapefileの概要を表示し、ALB点群の範囲と重なる藻場を調べる。

使い方: python scripts/inspect_moba.py data/raw/moba/mo2018_utm54/mo2018_utm54.shp data/work/alb/08OE2670.las
"""
import sys

import geopandas as gpd
import laspy
import pyogrio
from shapely.geometry import box

# LASに座標系が入っていないため、図郭番号 08OE2670 の「08」から
# 平面直角座標系 第Ⅷ系（JGD2011）と判断する
ALB_CRS = "EPSG:6676"

shp_path, las_path = sys.argv[1], sys.argv[2]

print("## 藻場Shapefile")
info = pyogrio.read_info(shp_path)
print(f"座標系: {info['crs']}")
print(f"件数: {info['features']:,}")
print(f"図形の種類: {info['geometry_type']}")
print(f"全体の範囲: {info['total_bounds']}")
print("属性:")
for name, dtype in zip(info["fields"], info["dtypes"]):
    print(f"  {name} ({dtype})")

# 属性の中身の例（図形は読まずに表だけ読むので速い）
attrs = pyogrio.read_dataframe(shp_path, read_geometry=False)
print("\n先頭5件:")
print(attrs.head().to_string())
print("\n属性ごとの値の種類（20種類以下のもの）:")
for col in attrs.columns:
    vc = attrs[col].value_counts(dropna=False)
    if len(vc) <= 20:
        print(f"- {col}: " + ", ".join(f"{k}={v:,}" for k, v in vc.items()))

print("\n## ALBの範囲との重なり")
h = laspy.open(las_path).header
alb_area = gpd.GeoSeries([box(h.mins[0], h.mins[1], h.maxs[0], h.maxs[1])], crs=ALB_CRS)
alb_in_shp_crs = alb_area.to_crs(info["crs"])
print(f"ALBの範囲（{ALB_CRS}）: {[round(v, 2) for v in alb_area.total_bounds]}")
print(f"ALBの範囲（藻場の座標系に変換）: {[round(v, 2) for v in alb_in_shp_crs.total_bounds]}")
print(f"ALBの範囲（緯度経度）: {[round(v, 5) for v in alb_area.to_crs('EPSG:4326').total_bounds]}")

# 範囲（四角形）に引っかかる図形だけ読み込み、本当に重なるものを残す
near = gpd.read_file(shp_path, bbox=tuple(alb_in_shp_crs.total_bounds))
hit = near[near.intersects(alb_in_shp_crs.iloc[0])].copy()
print(f"重なる藻場: {len(hit)} 件")
if len(hit):
    # Webメルカトルのままだと面積が大きく出るので、平面直角座標系に変換して測る
    hit = hit.to_crs(ALB_CRS)
    hit["藻場全体の面積_m2"] = hit.area.round(1)
    hit["重なる面積_m2"] = hit.intersection(alb_area.iloc[0]).area.round(1)
    # 後の作業で使えるよう、重なる藻場だけを保存しておく
    hit.to_file("data/work/moba_in_alb.gpkg", driver="GPKG")
    print(hit.drop(columns="geometry").to_string())
    print(f"重なる面積の合計: {hit['重なる面積_m2'].sum():,.1f} m2 "
          f"（ALB範囲 {alb_area.area.iloc[0]:,.0f} m2 の {hit['重なる面積_m2'].sum() / alb_area.area.iloc[0]:.1%}）")
