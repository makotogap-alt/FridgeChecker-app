# FridgeChecker-app
# FridgeChecker-app
# 第4週：賞味期限管理

食材登録時に賞味期限を任意で設定できる。未入力と既存の食材は「未設定」と表示する。
日本時間の今日と比較し、昨日以前は「期限切れ」、当日は「本日まで」、1〜3日後は「あとN日」と表示する。
4日後以降は「期限まで余裕あり」と表示する。表示はページを開いた時・再読み込みした時に更新する。

## 起動・配備

```sh
pip install -r requirements.txt
sh start.sh
```

Renderでは、この変更を取り込んだ後、Start Commandを `sh start.sh` に設定する。
起動前に既存のfoodテーブルへ任意の日付カラムを追加する。既存データは削除せず、再実行時は追加済みのカラムを変更しない。
本番のDATABASE_URLには既存のPostgreSQL接続先を使用する。
DATABASE_URLが未設定の場合はSQLiteを使用するため、Renderの一時ファイルシステムでは再配備後の永続化は保証されない。
配備前にはデータベースのバックアップを取得する。

ローカル開発では `python migrate.py` の後に `python app.py` でも起動できる。

## テスト

```sh
pip install -r requirements-dev.txt
python -m pytest -q
```

テストは専用のメモリ内SQLiteで実施する。日付判定、入力検証、登録・再取得、日本時間、既存データの移行を確認する。
PostgreSQLとRenderの実環境は別途確認が必要である。

## 公開後の確認

賞味期限が昨日・今日・3日後・4日後の食材と未設定の食材を登録し、表示と再読み込み後の保存を確認する。
既存の食材が残っていることも確認する。
