Fridge Checker 第8週：品質改善・完成版

変更点
- 正常なデータだけ登録・変更できるよう、数量0〜10000の範囲検証を追加
- 入力ミス・未存在データ・サーバーエラー専用の説明ページ
- 購入で在庫数量が上限を超える操作を拒否（買い物リストは削除しない）
- 同期APIの応答が8秒以上かかった場合に通信エラーを表示
- 以前の第7週テスト6件に第8週の追加テスト10件を統合
- .gitignoreでDBや環境変数ファイルの誤コミットを防止（既に追跡されたDBには別途git rm --cachedが必要）

インストール:
  python3 -m pip install -r requirements-dev.txt

自動テスト:
  python3 -m unittest discover -s tests -v
  python3 -m pytest -q tests/test_week7.py

ローカル起動:
  python3 app.py
  http://127.0.0.1:5000

デプロイ:
  1. 実データベースのバックアップを作る
  2. テスト成功後、変更をgit pushする
  3. RenderのLogsとWeb ServiceのDeploy結果を確認する
  4. PC/スマホで登録・数量変更・検索・購入・同期を試す

注意:
  本アプリはユーザーログイン・CSRF対策がまだありません。
  公開URLを知る第三者が操作できます。本格的な家族利用前に認証を追加してください。
