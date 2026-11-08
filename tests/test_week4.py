"""第4週の回帰テスト。実行: python -m unittest discover -s tests -v"""
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


class Week4Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.tempdir.name) / "legacy.db"
        with sqlite3.connect(cls.db_path) as connection:
            connection.execute(
                "CREATE TABLE food (id INTEGER PRIMARY KEY, "
                "name VARCHAR(100) NOT NULL, quantity INTEGER NOT NULL, "
                "unit VARCHAR(20) NOT NULL)"
            )
            connection.execute(
                "INSERT INTO food (name, quantity, unit) VALUES ('保存済みの牛乳', 2, '本')"
            )
        os.environ["DATABASE_URL"] = f"sqlite:///{cls.db_path}"
        from app import app, db, Food
        cls.app, cls.db, cls.Food = app, db, Food
        cls.client = app.test_client()

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            cls.db.session.remove()
            cls.db.engine.dispose()
        cls.tempdir.cleanup()

    def test_01_migration_preserves_food(self):
        with self.app.app_context():
            food = self.Food.query.filter_by(name="保存済みの牛乳").one()
            self.assertEqual(food.quantity, 2)
            self.assertIsNone(food.expiration_date)

    def test_02_add_and_show_expiration(self):
        today = datetime.now(ZoneInfo("Asia/Tokyo")).date()
        soon = (today + timedelta(days=2)).isoformat()
        response = self.client.post(
            "/add",
            data={"name": "ヨーグルト", "quantity": "3",
                  "unit": "個", "expiration_date": soon},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("あと2日".encode(), response.data)

    def test_03_expired_update_and_delete(self):
        today = datetime.now(ZoneInfo("Asia/Tokyo")).date()
        yesterday = (today - timedelta(days=1)).isoformat()
        response = self.client.post("/add", data={
            "name": "卵", "quantity": "5",
            "unit": "個", "expiration_date": yesterday
        })
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            food_id = self.Food.query.filter_by(name="卵").one().id
        self.assertIn("期限切れ".encode(), self.client.get("/").data)
        self.assertEqual(
            self.client.post(f"/update/{food_id}", data={
                "quantity": "4", "expiration_date": ""
            }).status_code, 302
        )
        with self.app.app_context():
            updated = self.db.session.get(self.Food, food_id)
            self.assertEqual(updated.quantity, 4)
            self.assertIsNone(updated.expiration_date)
        self.assertEqual(
            self.client.post(f"/delete/{food_id}").status_code, 302
        )
        with self.app.app_context():
            self.assertIsNone(self.db.session.get(self.Food, food_id))

    def test_04_invalid_date_rejected(self):
        response = self.client.post("/add", data={
            "name": "失敗", "quantity": "1", "unit": "個",
            "expiration_date": "2026-02-30"
        })
        self.assertEqual(response.status_code, 400)
