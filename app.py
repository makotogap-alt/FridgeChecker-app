import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, redirect, render_template, request, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text

app = Flask(__name__)

# RenderではDATABASE_URLにPostgreSQLの接続URLを設定します。
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///fridge.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# 不自然に大きい入力を拒否し、データベースを保護します。
MAX_QUANTITY = 10000

# 第7週：食材カテゴリ
CATEGORIES = (
    "野菜", "肉・魚", "乳製品", "卵", "飲料", "調味料", "その他"
)


class Food(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit = db.Column(db.String(20), nullable=False)
    expiration_date = db.Column(db.Date, nullable=True)
    category = db.Column(db.String(20), nullable=False, default="その他")


class ShoppingItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit = db.Column(db.String(20), nullable=False)


def parse_expiration_date(value):
    if not value or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError("賞味期限の形式が正しくありません") from exc


def parse_category(value):
    if value not in CATEGORIES:
        raise ValueError("カテゴリを正しく選択してください")
    return value


# 第6週：複数端末で共有する情報をJSON向けに整理
# 第7週：categoryも含め、他端末でのカテゴリ変更を検知できるようにします。
def get_sync_snapshot(foods=None, shopping_items=None):
    if foods is None:
        foods = Food.query.order_by(Food.id).all()
    if shopping_items is None:
        shopping_items = ShoppingItem.query.order_by(ShoppingItem.id).all()

    return {
        "today": datetime.now(ZoneInfo("Asia/Tokyo")).date().isoformat(),
        "foods": [
            {
                "id": food.id,
                "name": food.name,
                "quantity": food.quantity,
                "unit": food.unit,
                "expiration_date": (
                    food.expiration_date.isoformat()
                    if food.expiration_date else None
                ),
                "category": food.category,
            }
            for food in foods
        ],
        "shopping_items": [
            {
                "id": item.id,
                "name": item.name,
                "quantity": item.quantity,
                "unit": item.unit,
            }
            for item in shopping_items
        ],
    }


# 第8週：入力ミスや存在しないURLを分かりやすい画面で案内
def input_error(message):
    return render_template(
        "error.html", title="入力内容を確認してください", message=message
    ), 400


@app.errorhandler(404)
def not_found(error):
    return render_template(
        "error.html", title="ページが見つかりません",
        message="指定された食材やページが見つかりません。"
    ), 404


@app.errorhandler(500)
def server_error(error):
    db.session.rollback()
    return render_template(
        "error.html", title="サーバーエラー",
        message="処理に失敗しました。時間をおいて再度お試しください。"
    ), 500


@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@app.route("/api/state", methods=["GET"])
def api_state():
    response = jsonify(get_sync_snapshot())
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/")
def index():
    foods = Food.query.order_by(Food.id).all()
    shopping_items = ShoppingItem.query.order_by(ShoppingItem.id).all()
    today = datetime.now(ZoneInfo("Asia/Tokyo")).date()
    return render_template(
        "index.html",
        foods=foods,
        shopping_items=shopping_items,
        today=today,
        soon_date=today + timedelta(days=3),
        categories=CATEGORIES,
        snapshot=get_sync_snapshot(foods, shopping_items),
    )


@app.route("/add", methods=["POST"])
def add_food():
    name = request.form.get("name", "").strip()
    unit = request.form.get("unit", "").strip()
    if not name or len(name) > 100:
        return input_error("食材名を1〜100文字で入力してください")
    if unit not in ("個", "本", "袋", "パック"):
        return input_error("単位が正しくありません")

    try:
        quantity = int(request.form.get("quantity", ""))
        expiration_date = parse_expiration_date(
            request.form.get("expiration_date", "")
        )
        category = parse_category(request.form.get("category", "その他"))
    except ValueError:
        return input_error("数量・賞味期限・カテゴリが正しくありません")

    if not 1 <= quantity <= MAX_QUANTITY:
        return input_error("数量は1〜10000の範囲で入力してください")

    db.session.add(Food(
        name=name, quantity=quantity, unit=unit,
        expiration_date=expiration_date, category=category,
    ))
    db.session.commit()
    return redirect(url_for("index"))


@app.route("/update/<int:food_id>", methods=["POST"])
def update_food(food_id):
    food = Food.query.get_or_404(food_id)
    try:
        quantity = int(request.form.get("quantity", ""))
        expiration_date = (
            parse_expiration_date(request.form.get("expiration_date"))
            if "expiration_date" in request.form
            else food.expiration_date
        )
        category = parse_category(request.form.get("category", food.category))
    except ValueError:
        return input_error("数量・賞味期限・カテゴリが正しくありません")

    if not 0 <= quantity <= MAX_QUANTITY:
        return input_error("数量は0〜10000の範囲で入力してください")

    food.quantity = quantity
    food.expiration_date = expiration_date
    food.category = category
    db.session.commit()
    return redirect(url_for("index"))


@app.route("/delete/<int:food_id>", methods=["POST"])
def delete_food(food_id):
    food = Food.query.get_or_404(food_id)
    db.session.delete(food)
    db.session.commit()
    return redirect(url_for("index"))


@app.route("/shopping/add", methods=["POST"])
def add_shopping_item():
    name = request.form.get("name", "").strip()
    unit = request.form.get("unit", "").strip()
    try:
        quantity = int(request.form.get("quantity", ""))
    except ValueError:
        return input_error("数量は整数で入力してください")

    if not name or len(name) > 100:
        return input_error("食材名を1〜100文字で入力してください")
    if unit not in ("個", "本", "袋", "パック"):
        return input_error("正しい単位を選択してください")
    if not 1 <= quantity <= MAX_QUANTITY:
        return input_error("数量は1〜10000の範囲で入力してください")

    db.session.add(ShoppingItem(name=name, quantity=quantity, unit=unit))
    db.session.commit()
    return redirect(url_for("index"))


@app.route("/shopping/delete/<int:item_id>", methods=["POST"])
def delete_shopping_item(item_id):
    item = ShoppingItem.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    return redirect(url_for("index"))


@app.route("/shopping/buy/<int:item_id>", methods=["POST"])
def buy_shopping_item(item_id):
    item = ShoppingItem.query.get_or_404(item_id)
    try:
        expiration_date = parse_expiration_date(
            request.form.get("expiration_date", "")
        )
        category = parse_category(request.form.get("category", "その他"))
    except ValueError:
        return input_error("賞味期限・カテゴリが正しくありません")

    # 賞味期限とカテゴリが同じ在庫だけを合算します。
    food = Food.query.filter_by(
        name=item.name, unit=item.unit,
        expiration_date=expiration_date, category=category,
    ).first()
    if food:
        if food.quantity + item.quantity > MAX_QUANTITY:
            return input_error("購入後の数量が10000を超えます")
        food.quantity += item.quantity
    else:
        db.session.add(Food(
            name=item.name, quantity=item.quantity, unit=item.unit,
            expiration_date=expiration_date, category=category,
        ))

    db.session.delete(item)
    db.session.commit()
    return redirect(url_for("index"))


# db.create_all()は既存テーブルへ列を追加しません。
# 既存レコードを消さず、第4週と第7週の列だけを補います。
def initialize_database():
    with app.app_context():
        db.create_all()
        if db.engine.dialect.name == "postgresql":
            with db.engine.begin() as connection:
                connection.execute(text(
                    "ALTER TABLE food ADD COLUMN IF NOT EXISTS expiration_date DATE"
                ))
                connection.execute(text(
                    "ALTER TABLE food ADD COLUMN IF NOT EXISTS category "
                    "VARCHAR(20) NOT NULL DEFAULT 'その他'"
                ))
        elif db.engine.dialect.name == "sqlite":
            columns = {
                column["name"]
                for column in inspect(db.engine).get_columns("food")
            }
            with db.engine.begin() as connection:
                if "expiration_date" not in columns:
                    connection.execute(text(
                        "ALTER TABLE food ADD COLUMN expiration_date DATE"
                    ))
                if "category" not in columns:
                    connection.execute(text(
                        "ALTER TABLE food ADD COLUMN category "
                        "VARCHAR(20) NOT NULL DEFAULT 'その他'"
                    ))
        else:
            raise RuntimeError("対応していないデータベースです")


initialize_database()

if __name__ == "__main__":
    app.run(debug=True)
