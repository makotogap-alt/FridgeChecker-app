import os
from datetime import date, timedelta

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest
from sqlalchemy import text
from app import app, db, Food, expiry_status
from migrate import upgrade


@pytest.fixture(autouse=True)
def database():
    app.config["TESTING"] = True
    with app.app_context():
        db.drop_all()
        db.create_all()
        yield
        db.session.remove()
        db.drop_all()


@pytest.mark.parametrize("offset,status,label", [
    (-1, "expired", "期限切れ"),
    (0, "soon", "本日まで"),
    (1, "soon", "あと1日"),
    (3, "soon", "あと3日"),
    (4, "fresh", "期限まで余裕あり"),
])
def test_boundaries(offset, status, label):
    today = date(2026, 10, 31)
    assert expiry_status(today + timedelta(days=offset), today) == (status, label)


def test_unset():
    assert expiry_status(None, date(2026, 10, 25)) == ("unset", "未設定")


@pytest.mark.parametrize("expiry", ["2026-10-25", "", "2024-02-29"])
def test_register_and_reload(expiry):
    client = app.test_client()
    response = client.post("/add", data={"name": "牛乳", "quantity": "2", "unit": "本", "expiry_date": expiry})
    assert response.status_code == 302
    db.session.remove()
    food = Food.query.one()
    assert food.expiry_date == (date.fromisoformat(expiry) if expiry else None)
    assert food.quantity == 2
    page = client.get("/")
    assert page.status_code == 200
    assert (expiry or "未設定") in page.get_data(as_text=True)


@pytest.mark.parametrize("expiry", ["2026-02-29", "2026-13-01", "abc", "20261025", "2026-1-1"])
def test_invalid_date_does_not_save(expiry):
    response = app.test_client().post("/add", data={"name": "牛乳", "quantity": "1", "unit": "本", "expiry_date": expiry})
    assert response.status_code == 400
    assert Food.query.count() == 0


def test_old_form_without_expiry():
    response = app.test_client().post("/add", data={"name": "卵", "quantity": "1", "unit": "パック"})
    assert response.status_code == 302
    assert Food.query.one().expiry_date is None


def test_migration_preserves_food_and_can_repeat():
    db.drop_all()
    with db.engine.begin() as connection:
        connection.execute(text("CREATE TABLE food (id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL, quantity INTEGER NOT NULL, unit VARCHAR(20) NOT NULL)"))
        connection.execute(text("INSERT INTO food VALUES (1, '牛乳', 2, '本')"))
    upgrade()
    upgrade()
    food = Food.query.one()
    assert (food.name, food.quantity, food.unit, food.expiry_date) == ("牛乳", 2, "本", None)


def test_japan_date_and_badges(monkeypatch):
    import app as module
    from datetime import datetime, timezone

    class Clock:
        @staticmethod
        def now(tz):
            return datetime(2026, 10, 24, 16, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(module, "datetime", Clock)
    for day in (24, 25, 28, 29):
        db.session.add(Food(name=f"食材{day}", quantity=1, unit="個", expiry_date=date(2026, 10, day)))
    db.session.commit()
    page = app.test_client().get("/").get_data(as_text=True)
    for value in ("今日：2026-10-25", "期限切れ", "本日まで", "あと3日", "期限まで余裕あり"):
        assert value in page
