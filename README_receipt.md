# Fridge Checker：Tesseract OCRでレシートを一括登録

既存の Flask / PostgreSQL / Render を維持しながら、OpenAI APIを使う画像認識部分を **サーバー内の Tesseract OCR** に置き換えました。日本語と英語の文字認識データをDockerに同梱してインストールします。

## 変わること・変わらないこと

- `/receipt` でレシート画像（JPEG / PNG / WebP、最大4MB）を撮影・アップロード。
- Tesseractで**日本語の文字を抽出**。よくある食品名をルールで識別し、食品・数量・カテゴリの**候補**を作成。
- 候補を編集・チェックし、OCR原文を参照して読み取り漏れの商品を追加できる。食品名を1件も自動抽出できないときも、OCRの原文から手入力へ進める。
- 「チェックした食品を一括登録する」を押したときだけ在庫へ反映。
- 同じ**画像ファイル**のSHA-256で二重登録をブロック。レビューの再送信もブロック。
- 既存の`Food`、`ShoppingItem`、同期API、検索、賞味期限表示、手入力一括登録を維持。
- **OpenAI APIキー不要。画像認識サービスへの送信なし。** アプリのDBにレシート画像は保存しない（OCR処理時の一時ファイルを除く）。
- **レシートの購入商品をすべて正確に読み取る保証はありません。** Tesseractは画像の文字を読むソフトであり、商品を理解するAIではありません。既知の食品名に一致しないものは自動候補にせず、原文からユーザーが追加してください。商品の規格（例：卵10個入り）と購入数量も確認してください。

## 重要：既存のRenderサービスの実行環境をDockerへ変更する

**DockerfileをGitHubへ追加しただけでは、現在のPythonランタイムからDockerに自動切替されません。** TesseractはOSレベルの実行ファイル・日本語言語データが必要なので、Dockerへ切り替えてください。

1. **最初にPostgreSQLのバックアップを確保。** 現在使用中のRenderサービスと`DATABASE_URL`、`SECRET_KEY`を確認。
2. ZIPに含まれるファイルをGitリポジトリ直下の対応する場所へ**上書き**する。既存の`app.py`、`templates/index.html`、`static/sync.js`などは変更する必要がありません。
3. Macで次を実行する（必ず`git status`で意図した変更だけか確認する）。

   ```bash
   git status
   git add Dockerfile .dockerignore requirements.txt receipt_service.py receipt_routes.py templates/receipt.html templates/receipt_review.html static/style.css tests/test_receipt.py tests/test_receipt_ocr.py README_receipt.md
   git commit -m "feat: レシート認識をTesseract OCRに変更"
   git push origin main
   ```

4. [Render Dashboard](https://dashboard.render.com/)で現在のFridge Checker Web Serviceを選択 → **Settings → Build → Source → Edit** → リポジトリとブランチを確認して **Runtime：Docker** を選び、**Dockerfile Path：`./Dockerfile`**（欄がある場合）で変更をデプロイする。RenderはDockerfileの `CMD` に従い起動します。
5. **Environment** では従来の`DATABASE_URL`（PostgreSQL）と`SECRET_KEY`（安全なランダム値）を**維持**する。`OPENAI_API_KEY`は不要。Dockerコンテナ内で使うため、MacにTesseractをインストールする必要はない。
6. **Logs**でDockerのビルド成功、Web ServiceがLiveになったことを確認し、`https://fridgechecker-app.onrender.com/receipt`からJPEG/PNG/WebPの日本語レシートを試す。レビュー画面で在庫に反映する前に候補・原文・数量を確認する。

Renderのランタイム切替UIが異なる場合は、公式の説明を参照してください：https://render.com/docs/native-runtimes

> 注意: `Dockerfile`を含むコミットをpushしても、RenderのランタイムをPythonのままにすると `tesseract` が見つからず認識できません。

## ローカルで動かすとき

### Dockerが利用できる場合

```bash
docker build -t fridgechecker-tesseract .
docker run --rm -p 5000:10000 \
  -e SECRET_KEY="$(python3 -c 'import secrets;print(secrets.token_hex(32))')" \
  fridgechecker-tesseract
```

上の例はローカルSQLiteで試す場合です。コンテナの終了でSQLiteのデータが消えるので、**本番データの検証には使わないでください。** 本番Renderは既存の`DATABASE_URL`に接続してください。

### Pythonで直接起動する場合

```bash
# macOS/Homebrewの場合（日本語言語データの導入はbrewの案内に従う）
brew install tesseract tesseract-lang
python3 -m pip install -r requirements-dev.txt
python3 app.py
```

テスト：

```bash
python3 -m unittest discover -s tests -p 'test_receipt_ocr.py' -v
python3 -m unittest discover -s tests -p 'test_receipt.py' -v
python3 -m unittest discover -s tests -p 'test_week7.py' -v
```

## 補足

- `receipt_import`テーブルを使った二重登録防止は画像ファイル単位です。同じレシートを撮影し直した**別画像**までは検知できません。
- 現状のアプリ全体には**ログイン・認可・既存フォームへのCSRF対策がありません**。公開URLを知る第三者が操作できるため、本格的な家族利用の前に保護を追加してください。
- 有料の画像認識APIは使いませんが、Renderのサーバー費用が発生する場合があります。
- 今回のZIPはアプリのソースコードです。Render上へのデプロイ自体はユーザーのアカウントで操作する必要があります。
