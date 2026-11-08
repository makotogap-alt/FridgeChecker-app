
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from flask import Flask, render_template, request, redirect, url_for
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


# 食材のデータベース
class Food(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit = db.Column(db.String(20), nullable=False)

    # 第4週：賞味期限を追加
    expiration_date = db.Column(db.Date, nullable=True)


# 賞味期限を日付型に変換
def parse_expiration_date(value):
    if not value or not value.strip():
        return None

    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise ValueError("賞味期限の形式が正しくありません")


# トップページ
@app.route("/")
def index():
    foods = Food.query.all()

    today = datetime.now(ZoneInfo("Asia/Tokyo")).date()
    soon_date = today + timedelta(days=3)

    return render_template(
        "index.html",
        foods=foods,
        today=today,
        soon_date=soon_date
    )


# 食材の追加
@app.route("/add", methods=["POST"])
def add_food():
    name = request.form.get("name", "").strip()
    unit = request.form.get("unit", "").strip()

    if not name or not unit:
        return "食材名と単位を入力してください", 400

    try:
        quantity = int(request.form.get("quantity", ""))
        expiration_date = parse_expiration_date(
            request.form.get("expiration_date", "")
        )
    except ValueError:
        return "数量または賞味期限が正しくありません", 400

    if quantity < 1:
        return "数量は1以上にしてください", 400

    food = Food(
        name=name,
        quantity=quantity,
        unit=unit,
        expiration_date=expiration_date
    )

    db.session.add(food)
    db.session.commit()

    return redirect(url_for("index"))


# 食材の変更
@app.route("/update/<int:food_id>", methods=["POST"])
def update_food(food_id):
    food = Food.query.get_or_404(food_id)

    try:
        quantity = int(request.form.get("quantity", ""))

        if "expiration_date" in request.form:
            expiration_date = parse_expiration_date(
                request.form.get("expiration_date")
            )
        else:
            expiration_date = food.expiration_date

    except ValueError:
        return "数量または賞味期限が正しくありません", 400

    if quantity < 0:
        return "数量は0以上にしてください", 400

    food.quantity = quantity
    food.expiration_date = expiration_date

    db.session.commit()

    return redirect(url_for("index"))


# 食材の削除
@app.route("/delete/<int:food_id>", methods=["POST"])
def delete_food(food_id):
    food = Food.query.get_or_404(food_id)

    db.session.delete(food)
    db.session.commit()

    return redirect(url_for("index"))


# 既存の食材データを残して賞味期限の列を追加
def initialize_database():
    with app.app_context():
        db.create_all()

        if db.engine.dialect.name == "postgresql":
            with db.engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER TABLE food "
                        "ADD COLUMN IF NOT EXISTS expiration_date DATE"
                    )
                )
        else:
            columns = {
                column["name"]
                for column in inspect(db.engine).get_columns("food")
            }

            if "expiration_date" not in columns:
                with db.engine.begin() as connection:
                    connection.execute(
                        text(
                            "ALTER TABLE food "
                            "ADD COLUMN expiration_date DATE"
                        )
                    )


initialize_database()


if __name__ == "__main__":
    app.run(debug=True)
