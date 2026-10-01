from flask import Flask

app = Flask(__name__)

@app.route("/")
def index():
    return """
    <h1>冷蔵庫に何ある？</h1>
    <p>冷蔵庫の中身を確認できるWebアプリです。</p>
    """

if __name__ == "__main__":
    app.run(debug=True)