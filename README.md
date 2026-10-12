# グリーンレーザ(ALB)で見る伊豆の藻場ポテンシャル

## 目的

SotM Asia OSAKA での Honey Fombuena さんの発表をきっかけに、藻場を壊さずに広い範囲を測れるグリーンレーザ（ALB：航空レーザ測深）の点群データを初めて使ってみるソロハッカソンです。

## 公開ページ

https://furuhashilab.github.io/greenlaser-seagrass/

## フォルダ構成

| フォルダ | 内容 |
|---|---|
| `docs/` | GitHub Pages で公開する Web ページ（`index.html` と `docs/data/`） |
| `scripts/` | データ処理用の Python スクリプト |
| `data/raw/` | ダウンロードした元データ（git に含めない） |
| `data/work/` | 処理途中のファイル（git に含めない） |

## 使用データの出典

| データ名 | 提供元 | ライセンス | URL |
|---|---|---|---|
| VIRTUAL SHIZUOKA 静岡県 伊豆西部 点群データ ALBデータ（オリジナル・グラウンドデータ、グリッドデータ）図郭 08OE2670 | 静岡県（G空間情報センター） | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.ja)（CC BY 4.0 / ODbL のデュアルライセンスのうち CC BY 4.0 を選択） | https://www.geospatial.jp/ckan/dataset/shizuoka-2020-pointcloud |
| 自然環境保全基礎調査 藻場調査2018-2020（UTM54） | 環境省自然環境局 生物多様性センター（環境ジオポータル） | 提供元の利用規約（政府標準利用規約 第2.0版）に基づき利用 | https://geoportal.env.go.jp/datasets/1209759c6d614dacad11f48b9e113032_0/about |

どちらのデータも、このリポジトリで加工して使っています。藻場タイプの凡例は https://www.biodic.go.jp/moba/1_3_7.html を参照しています。データの調査メモは [docs/notes.md](docs/notes.md) にあります。

## ライセンス

この成果物は [クリエイティブ・コモンズ 表示 4.0 国際（CC BY 4.0）](https://creativecommons.org/licenses/by/4.0/deed.ja) で公開します。全文は [LICENSE](LICENSE) を見てください。

© 作者名

※ 使用データにはそれぞれのライセンスが適用されます。上の「使用データの出典」を見てください。
