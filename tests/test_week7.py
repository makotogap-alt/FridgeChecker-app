"""実行例：python3 -m unittest discover -s tests -v"""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path


class Week7Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 第6週までのデータが入っているSQLiteを模したDB
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db_file = Path(cls.tmp.name) / "existing.db"
        with sqlite3.connect(cls.db_file) as connection:
            connection.execute(
                "CREATE TABLE food (id INTEGER PRIMARY KEY, "
                "name VARCHAR(100) NOT NULL, quantity INTEGER NOT NULL, "
                "unit VARCHAR(20) NOT NULL, expiration_date DATE)"
            )
            connection.execute(
                "INSERT INTO food (name, quantity, unit) "
                "VALUES ('以前の牛乳', 2, '本')"
            )
        os.environ["DATABASE_URL"] = f"sqlite:///{cls.db_file}"

        # DBの環境変数を設定してからアプリを読み込む
        from app import app, db, Food, ShoppingItem
        cls.app, cls.db = app, db
        cls.Food, cls.ShoppingItem = Food, ShoppingItem
        cls.client = app.test_client()

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            cls.db.session.remove()
            cls.db.engine.dispose()
        cls.tmp.cleanup()

    def test_01_migration_keeps_existing_food(self):
        with self.app.app_context():
            old = self.Food.query.filter_by(name="以前の牛乳").one()
            self.assertEqual(old.quantity, 2)
            self.assertEqual(old.category, "その他")

    def test_02_add_and_filter_markup(self):
        response = self.client.post("/add", data={
            "name": "トマト", "quantity": "3", "unit": "個",
            "category": "野菜", "expiration_date": "2026-11-20",
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('data-name="トマト"'.encode(), response.data)
        self.assertIn('data-category="野菜"'.encode(), response.data)
        self.assertIn(b'id="food-search"', response.data)
        self.assertIn(b'id="food-category-filter"', response.data)

    def test_03_update_category(self):
        with self.app.app_context():
            food_id = self.Food.query.filter_by(name="トマト").one().id
        response = self.client.post(f"/update/{food_id}", data={
            "quantity": "2", "category": "その他",
            "expiration_date": "2026-11-20",
        })
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            food = self.db.session.get(self.Food, food_id)
            self.assertEqual(food.category, "その他")
            self.assertEqual(food.quantity, 2)

    def test_04_purchase_preserves_category(self):
        self.assertEqual(self.client.post("/shopping/add", data={
            "name": "チーズ", "quantity": "2", "unit": "個",
        }).status_code, 302)
        with self.app.app_context():
            item_id = self.ShoppingItem.query.filter_by(name="チーズ").one().id
        response = self.client.post(f"/shopping/buy/{item_id}", data={
            "category": "乳製品", "expiration_date": "2026-12-01",
        })
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertEqual(self.Food.query.filter_by(
                name="チーズ", category="乳製品"
            ).one().quantity, 2)
            self.assertIsNone(self.db.session.get(self.ShoppingItem, item_id))

    def test_05_reject_unknown_category(self):
        response = self.client.post("/add", data={
            "name": "テスト", "quantity": "1", "unit": "個",
            "category": "不正なカテゴリ",
        })
        self.assertEqual(response.status_code, 400)

    def test_06_sync_api_includes_category(self):
        response = self.client.get("/api/state")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("category", data["foods"][0])
        self.assertEqual(response.headers["Cache-Control"], "no-store")


    # 第8週：不正な入力に対するエラー表示・データ保護
    def test_07_invalid_registration_returns_readable_400(self):
        valid = {"name": "検証用", "quantity": "1", "unit": "個", "category": "その他"}
        cases = [
            {"name": ""}, {"name": "あ" * 101},
            {"quantity": "abc"}, {"quantity": "0"},
            {"quantity": "-1"}, {"quantity": "10001"},
            {"unit": "不正な単位"}, {"category": "不正なカテゴリ"},
            {"expiration_date": "2026-02-30"},
        ]
        with self.app.app_context():
            before = self.Food.query.count()
        for change in cases:
            with self.subTest(change=change):
                response = self.client.post("/add", data={**valid, **change})
                self.assertEqual(response.status_code, 400)
                self.assertIn("入力内容を確認してください".encode(), response.data)
        with self.app.app_context():
            self.assertEqual(self.Food.query.count(), before)

    def test_08_invalid_update_does_not_change_saved_data(self):
        self.client.post("/add", data={
            "name": "第8週更新検証", "quantity": "3", "unit": "本",
            "category": "飲料", "expiration_date": "2026-12-05",
        })
        with self.app.app_context():
            food_id = self.Food.query.filter_by(name="第8週更新検証").one().id
        for values in (
            {"quantity": "-2", "category": "飲料"},
            {"quantity": "2", "category": "不正"},
            {"quantity": "10001", "category": "飲料"},
            {"quantity": "2", "category": "飲料", "expiration_date": "2026-02-30"},
        ):
            with self.subTest(values=values):
                response = self.client.post(f"/update/{food_id}", data=values)
                self.assertEqual(response.status_code, 400)
        with self.app.app_context():
            food = self.db.session.get(self.Food, food_id)
            self.assertEqual(food.quantity, 3)
            self.assertEqual(food.category, "飲料")
            self.assertEqual(food.expiration_date.isoformat(), "2026-12-05")

    def test_09_shopping_validation_and_delete(self):
        invalids = [
            {"name": ""}, {"quantity": "abc"}, {"quantity": "0"},
            {"quantity": "10001"}, {"unit": "本箱"},
        ]
        with self.app.app_context():
            initial = self.ShoppingItem.query.count()
        for patch in invalids:
            response = self.client.post("/shopping/add", data={
                "name": "第8週無効", "quantity": "1", "unit": "個", **patch
            })
            self.assertEqual(response.status_code, 400)
        with self.app.app_context():
            self.assertEqual(self.ShoppingItem.query.count(), initial)
        self.assertEqual(self.client.post("/shopping/add", data={
            "name": "第8週削除", "quantity": "2", "unit": "袋"
        }).status_code, 302)
        with self.app.app_context():
            item_id = self.ShoppingItem.query.filter_by(name="第8週削除").one().id
        self.assertEqual(self.client.post(f"/shopping/delete/{item_id}").status_code, 302)
        with self.app.app_context():
            self.assertIsNone(self.db.session.get(self.ShoppingItem, item_id))

    def test_10_purchased_food_merges_matching_stock(self):
        expires = "2026-12-20"
        self.client.post("/add", data={
            "name": "第8週牛乳", "quantity": "1", "unit": "本",
            "category": "乳製品", "expiration_date": expires
        })
        self.client.post("/shopping/add", data={
            "name": "第8週牛乳", "quantity": "2", "unit": "本"
        })
        with self.app.app_context():
            item_id = self.ShoppingItem.query.filter_by(name="第8週牛乳").one().id
        response = self.client.post(f"/shopping/buy/{item_id}", data={
            "category": "乳製品", "expiration_date": expires
        })
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            matches = self.Food.query.filter_by(name="第8週牛乳").all()
            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0].quantity, 3)
            self.assertIsNone(self.db.session.get(self.ShoppingItem, item_id))

    def test_11_purchasing_different_expiration_creates_separate_stock(self):
        self.client.post("/add", data={
            "name": "第8週ヨーグルト", "quantity": "1", "unit": "個",
            "category": "乳製品", "expiration_date": "2026-12-01"
        })
        self.client.post("/shopping/add", data={
            "name": "第8週ヨーグルト", "quantity": "2", "unit": "個"
        })
        with self.app.app_context():
            item_id = self.ShoppingItem.query.filter_by(name="第8週ヨーグルト").one().id
        self.assertEqual(self.client.post(f"/shopping/buy/{item_id}", data={
            "category": "乳製品", "expiration_date": "2026-12-02"
        }).status_code, 302)
        with self.app.app_context():
            matches = self.Food.query.filter_by(name="第8週ヨーグルト").all()
            self.assertEqual(sorted(food.quantity for food in matches), [1, 2])

    def test_12_expiration_messages_at_boundary(self):
        from datetime import timedelta
        from zoneinfo import ZoneInfo
        from datetime import datetime
        today = datetime.now(ZoneInfo("Asia/Tokyo")).date()
        for name, offset in (
            ("第8週期限切れ", -1), ("第8週今日", 0),
            ("第8週三日", 3), ("第8週四日", 4),
        ):
            self.client.post("/add", data={
                "name": name, "quantity": "1", "unit": "個",
                "category": "その他",
                "expiration_date": (today + timedelta(days=offset)).isoformat()
            })
        html = self.client.get("/").data.decode("utf-8")
        for message in ("期限切れ", "本日まで", "あと3日", "期限内"):
            self.assertIn(message, html)

    def test_13_sync_api_reflects_updated_quantity(self):
        self.client.post("/add", data={
            "name": "第8週同期", "quantity": "3", "unit": "本",
            "category": "飲料"
        })
        data = self.client.get("/api/state").get_json()
        target = next(food for food in data["foods"] if food["name"] == "第8週同期")
        self.assertEqual(target["quantity"], 3)
        response = self.client.post(f"/update/{target['id']}", data={
            "quantity": "2", "category": "飲料"
        })
        self.assertEqual(response.status_code, 302)
        data = self.client.get("/api/state").get_json()
        updated = next(food for food in data["foods"] if food["id"] == target["id"])
        self.assertEqual(updated["quantity"], 2)

    def test_14_missing_items_and_security_headers(self):
        for path in ("/nothing-here", "/update/999999", "/shopping/buy/999999"):
            response = self.client.post(path) if "999999" in path else self.client.get(path)
            self.assertEqual(response.status_code, 404)
            self.assertIn("ページが見つかりません".encode(), response.data)
        response = self.client.get("/")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["Referrer-Policy"], "strict-origin-when-cross-origin")

    def test_15_migration_can_run_twice(self):
        from app import initialize_database
        initialize_database()
        initialize_database()
        with self.app.app_context():
            self.assertEqual(self.Food.query.filter_by(name="以前の牛乳").count(), 1)

    def test_16_reject_purchase_quantity_overflow(self):
        self.client.post("/add", data={
            "name": "第8週上限", "quantity": "9999", "unit": "個",
            "category": "その他", "expiration_date": "2026-12-25"
        })
        self.client.post("/shopping/add", data={
            "name": "第8週上限", "quantity": "2", "unit": "個"
        })
        with self.app.app_context():
            item_id = self.ShoppingItem.query.filter_by(name="第8週上限").one().id
        response = self.client.post(f"/shopping/buy/{item_id}", data={
            "category": "その他", "expiration_date": "2026-12-25"
        })
        self.assertEqual(response.status_code, 400)
        with self.app.app_context():
            self.assertEqual(self.Food.query.filter_by(name="第8週上限").one().quantity, 9999)
            self.assertIsNotNone(self.db.session.get(self.ShoppingItem, item_id))


if __name__ == "__main__":
    unittest.main()
