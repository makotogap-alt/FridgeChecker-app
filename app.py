import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from flask import Flask, render_template, request, redirect, url_for, jsonify
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

class ShoppingItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit = db.Column(db.String(20), nullable=False)


# 賞味期限を日付型に変換
def parse_expiration_date(value):
    if not value or not value.strip():
        return None

    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise ValueError("賞味期限の形式が正しくありません")
    

# 第6週：共有する食材データを取得
def get_sync_snapshot(foods=None, shopping_items=None):

    if foods is None:
        foods = Food.query.order_by(Food.id).all()

    if shopping_items is None:
        shopping_items = ShoppingItem.query.order_by(
            ShoppingItem.id
        ).all()

    today = datetime.now(ZoneInfo("Asia/Tokyo")).date()

    return {
        "today": today.isoformat(),

        "foods": [
            {
                "id": food.id,
                "name": food.name,
                "quantity": food.quantity,
                "unit": food.unit,
                "expiration_date": (
                    food.expiration_date.isoformat()
                    if food.expiration_date else None
                )
            }
            for food in foods
        ],

        "shopping_items": [
            {
                "id": item.id,
                "name": item.name,
                "quantity": item.quantity,
                "unit": item.unit
            }
            for item in shopping_items
        ]
    }


# 第6週：他の端末が最新情報を取得するAPI
@app.route("/api/state", methods=["GET"])
def api_state():

    data = get_sync_snapshot()

    response = jsonify(data)
    response.headers["Cache-Control"] = "no-store"

    return response



# トップページ

# トップページ
@app.route("/")
def index():

    foods = Food.query.order_by(Food.id).all()

    shopping_items = ShoppingItem.query.order_by(
        ShoppingItem.id
    ).all()

    today = datetime.now(ZoneInfo("Asia/Tokyo")).date()
    soon_date = today + timedelta(days=3)

    # 画面を開いた時点のデータを保存
    snapshot = get_sync_snapshot(
        foods,
        shopping_items
    )

    return render_template(
        "index.html",
        foods=foods,
        shopping_items=shopping_items,
        today=today,
        soon_date=soon_date,
        snapshot=snapshot
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


# 買い物リストへの登録
@app.route("/shopping/add", methods=["POST"])
def add_shopping_item():
    name = request.form.get("name", "").strip()
    unit = request.form.get("unit", "").strip()

    try:
        quantity = int(request.form.get("quantity", ""))
    except ValueError:
        return "数量は整数で入力してください", 400

    if not name or len(name) > 100:
        return "食材名を1〜100文字で入力してください", 400

    if unit not in ("個", "本", "袋", "パック"):
        return "正しい単位を選択してください", 400

    if quantity < 1:
        return "数量は1以上にしてください", 400

    item = ShoppingItem(
        name=name,
        quantity=quantity,
        unit=unit
    )

    db.session.add(item)
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


# 買い物リストから削除
@app.route("/shopping/delete/<int:item_id>", methods=["POST"])
def delete_shopping_item(item_id):
    item = ShoppingItem.query.get_or_404(item_id)

    db.session.delete(item)
    db.session.commit()

    return redirect(url_for("index"))


# 購入した食材を冷蔵庫へ追加
@app.route("/shopping/buy/<int:item_id>", methods=["POST"])
def buy_shopping_item(item_id):
    item = ShoppingItem.query.get_or_404(item_id)

    try:
        expiration_date = parse_expiration_date(
            request.form.get("expiration_date", "")
        )
    except ValueError:
        return "賞味期限の形式が正しくありません", 400

    # 同じ食材・単位・賞味期限の在庫を探す
    food = Food.query.filter_by(
        name=item.name,
        unit=item.unit,
        expiration_date=expiration_date
    ).first()

    if food:
        # 同じ条件の食材がある場合、数量を増やす
        food.quantity += item.quantity
    else:
        # 該当する在庫がなければ新しく登録する
        food = Food(
            name=item.name,
            quantity=item.quantity,
            unit=item.unit,
            expiration_date=expiration_date
        )
        db.session.add(food)

    # 買い物リストから削除
    db.session.delete(item)

    # 在庫更新とリスト削除をまとめて保存
    db.session.commit()

    return redirect(url_for("index"))



initialize_database()


if __name__ == "__main__":
    app.run(debug=True)
