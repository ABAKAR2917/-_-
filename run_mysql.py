import os

os.environ.setdefault("MYSQL_HOST", "127.0.0.1")
os.environ.setdefault("MYSQL_PORT", "3306")
os.environ.setdefault("MYSQL_USER", "root")
os.environ.setdefault("MYSQL_PASSWORD", "")
os.environ.setdefault("MYSQL_DATABASE", "employment_platform")

from app import app


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=False, use_reloader=False)
