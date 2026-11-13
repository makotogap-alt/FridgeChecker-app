# Fridge Checker: レシート一括登録 MVP

既存アプリの `app.py`, `index.html`, `style.css`, `sync.js`, `search.js` をベースにした追加機能です。

## 新機能

- `/receipt` でレシート画像（JPEG/PNG/WebP 4MB以内）をアップロード
- OpenAI Vision対応モデルを使い、食品名・数量・単位・カテゴリを抽出（任意設定）
- 認識内容を人間が確認・修正し、一括で在庫へ反映
- 賞味期限はレビュー画面で任意入力
- 同じ画像の重複登録を SHA-256 ハッシュで防止。レビューの二重送信も防止
- APIキーなしではカンマ区切りの商品一括入力を利用可能
- 登録は従来の `Food` テーブルに保存され、PC/スマホ間の既存同期APIにも反映
- 画像そのものはアプリのストレージやDBに保存しない。ただし認識APIへ送信する

## 実行

```bash
python3 -m pip install -r requirements-dev.txt
export SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
# 画像認識を使う場合だけ設定（有料API。ChatGPTの契約とは別です）
export OPENAI_API_KEY="YOUR_API_KEY"
python3 app.py
```

http://127.0.0.1:5000/ にアクセス →「レシートから登録する」。

テスト（開発環境で実行）:

```bash
python3 -m unittest discover -s tests -p 'test_receipt.py' -v
```

## Renderに反映するとき

1. 既存のPostgreSQLをバックアップ
2. ソースをプロジェクト構造に沿って配置。`app.py`, `receipt_routes.py`, `receipt_service.py` は同じ階層、HTMLは `templates/`、CSS/JSは `static/`
3. Render Web Service の Environment に `SECRET_KEY` を安全なランダム値で追加。画像認識を使う場合だけ `OPENAI_API_KEY` を追加。`DATABASE_URL` は従来の設定を保持
4. テストしてから GitHub に push → RenderのDeployとLogsを確認
5. 初回起動時に `receipt_import` テーブルが追加される（既存 `food` 等のテーブルを削除しない）

## 重要な制限

- **現在のアプリ全体にはログイン・認可・既存フォームのCSRF対策がありません。** 新しいレシートフォームだけにCSRFチェックを追加していますが、**本番サイトを家族向けに公開する前にアプリ全体のアクセス制御が必要**です。
- 画像認識はモデルの推測なので購入内容と違う場合があります。必ず確認してから登録してください。
- 手入力モードは内容が同じでも毎回登録されます。重複防止は画像アップロードに対して行っています。
- バーコード、購入履歴連携、消費予測、PWA化は今回の範囲外です。
- デプロイ・API実通信はこの作業環境から実行していません。
