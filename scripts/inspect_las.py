"""LASファイルの基本情報（点の数・範囲・座標系・分類コード）を表示する。

使い方: python scripts/inspect_las.py data/work/alb/08OE2670.las
"""
import sys

import laspy
import numpy as np

# ASPRS（LASの規格を決めている団体）が定めた分類コードの意味
ASPRS_CLASSES = {
    0: "未分類（作成されたまま）",
    1: "未分類",
    2: "地面",
    3: "低い植生",
    4: "中くらいの植生",
    5: "高い植生",
    6: "建物",
    7: "ノイズ（低い位置）",
    9: "水面",
    17: "橋",
    18: "ノイズ（高い位置）",
    40: "水底（測深点）",
    41: "水面（測深）",
    42: "水柱内の点",
    43: "水中の構造物",
    45: "水柱",
}

path = sys.argv[1]
las = laspy.read(path)
h = las.header

print("## ヘッダー")
print(f"LASバージョン: {h.version}  点のフォーマット: {h.point_format.id}")
print(f"点の数: {h.point_count:,}")
print(f"作成ソフト: {h.generating_software}  作成日: {h.creation_date}")
print(f"X 範囲: {h.mins[0]:.3f} 〜 {h.maxs[0]:.3f}")
print(f"Y 範囲: {h.mins[1]:.3f} 〜 {h.maxs[1]:.3f}")
print(f"Z 範囲: {h.mins[2]:.3f} 〜 {h.maxs[2]:.3f}")
print(f"スケール: {h.scales}  オフセット: {h.offsets}")
print(f"属性: {list(las.point_format.dimension_names)}")

print("\n## 座標系")
crs = h.parse_crs()
print(f"parse_crs(): {crs.to_string() if crs else 'なし（LASに座標系が書かれていない）'}")
for v in h.vlrs:
    print(f"VLR: {v.user_id} / {v.record_id} / {v.description}")

print("\n## 分類コード")
codes, counts = np.unique(np.asarray(las.classification), return_counts=True)
print("| コード | 意味（ASPRS標準） | 点数 | 割合 |")
print("|---:|---|---:|---:|")
for c, n in zip(codes, counts):
    print(f"| {c} | {ASPRS_CLASSES.get(int(c), '（標準にない独自コード）')} | {n:,} | {n / h.point_count:.1%} |")

print("\n## 分類コードごとの高さ（Z）")
cls = np.asarray(las.classification)
z = np.asarray(las.z)
for c in codes:
    zc = z[cls == c]
    print(f"コード {c}: 最小 {zc.min():.2f} / 中央値 {np.median(zc):.2f} / 最大 {zc.max():.2f}")
