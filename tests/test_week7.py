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


if __name__ == "__main__":
    unittest.main()
