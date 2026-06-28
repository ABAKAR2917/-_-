import argparse
import os

from werkzeug.security import generate_password_hash


def configure_mysql() -> None:
    os.environ.setdefault("MYSQL_HOST", "127.0.0.1")
    os.environ.setdefault("MYSQL_PORT", "3306")
    os.environ.setdefault("MYSQL_USER", "root")
    os.environ.setdefault("MYSQL_PASSWORD", "")
    os.environ.setdefault("MYSQL_DATABASE", "employment_platform")


def create_admin(email: str, password: str, full_name: str) -> None:
    configure_mysql()
    from app import app, execute

    with app.app_context():
        execute(
            """
            INSERT INTO users(full_name, email, password_hash, role, created_at)
            VALUES(?, ?, ?, 'admin', NOW())
            """,
            (full_name, email, generate_password_hash(password)),
        )
    print(f"Admin created: {email}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--create-admin", action="store_true")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--full-name", default="Администратор")
    args = parser.parse_args()

    if args.create_admin:
        create_admin(args.email, args.password, args.full_name)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
