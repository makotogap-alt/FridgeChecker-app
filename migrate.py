from sqlalchemy import inspect, text
from app import app, db


def upgrade():
    with db.engine.begin() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("food")}
        if "expiry_date" not in columns:
            connection.execute(text("ALTER TABLE food ADD COLUMN expiry_date DATE"))


if __name__ == "__main__":
    with app.app_context():
        upgrade()
    print("賞味期限カラムの準備が完了しました。")
