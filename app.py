import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from flask import Flask, redirect, render_template, request, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text

app = Flask(__name__)

database_url = os.environ.get("DATABASE_URL")
if database_url:
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///fridge.db"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


class Food(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit = db.Column(db.String(20), nullable=False)
    expiration_date = db.Column(db.Date, nullable=True)


def parse_expiration_date(value):
    """空欄は未設定、それ以外はHTMLの日付入力をdate型に変換する。"""
    if not value or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError("賞味期限は正しい日付を入力してください。") from exc


@app.route("/")
def index():
    foods = Food.query.all()
    today = datetime.now(ZoneInfo("Asia/Tokyo")).date()
    soon_date = today + timedelta(days=3)
    return render_template(
        "index.html", foods=foods, today=today, soon_date=soon_date
    )


@app.route("/add", methods=["POST"])
def add_food():
    name = request.form.get("name", "").strip()
    unit = request.form.get("unit", "").strip()
    if not name or not unit:
        return "食材名と単位を入力してください。", 400

    try:
        quantity = int(request.form.get("quantity", ""))
        expiration_date = parse_expiration_date(request.form.get("expiration_date", ""))
    except ValueError:
        return "数量または賞味期限の入力が正しくありません。", 400

    if quantity < 1:
        return "登録時の数量は1以上にしてください。", 400

    food = Food(
        name=name,
        quantity=quantity,
        unit=unit,
        expiration_date=expiration_date,
    )
    db.session.add(food)
    db.session.commit()
    return redirect(url_for("index"))


@app.route("/update/<int:food_id>", methods=["POST"])
def update_food(food_id):
    food = Food.query.get_or_404(food_id)

    try:
        quantity = int(request.form.get("quantity", ""))
        # 第3週の数量変更だけを行うフォームにも対応する。
        expiration_date = (
            parse_expiration_date(request.form.get("expiration_date"))
            if "expiration_date" in request.form
            else food.expiration_date
        )
    except ValueError:
        return "数量または賞味期限の入力が正しくありません。", 400

    if quantity < 0:
        return "数量は0以上にしてください。", 400

    food.quantity = quantity
    food.expiration_date = expiration_date
    db.session.commit()
    return redirect(url_for("index"))


@app.route("/delete/<int:food_id>", methods=["POST"])
def delete_food(food_id):
    food = Food.query.get_or_404(food_id)
    db.session.delete(food)
    db.session.commit()
    return redirect(url_for("index"))


def initialize_database():
    """第4週の追加カラムを既存の食材を消さずに用意する。

    db.create_all() は既存テーブルに列を追加しないため、
    food.expiration_date がまだ無いデータベースだけALTER TABLEする。
    本格的な複数カラムの変更には将来Alembic等を導入する。
    """
    with app.app_context():
        db.create_all()
        if db.engine.dialect.name == "postgresql":
            # PostgreSQLでは重複起動に備えIF NOT EXISTSを使用する。
            with db.engine.begin() as connection:
                connection.execute(
                    text("ALTER TABLE food ADD COLUMN IF NOT EXISTS expiration_date DATE")
                )
        else:
            column_names = {
                column["name"] for column in inspect(db.engine).get_columns("food")
            }
            if "expiration_date" not in column_names:
                with db.engine.begin() as connection:
                    connection.execute(
                        text("ALTER TABLE food ADD COLUMN expiration_date DATE")
                    )


initialize_database()

if __name__ == "__main__":
    app.run(debug=True)
