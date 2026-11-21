from __future__ import annotations

import os
import secrets
import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

import numpy as np
import pymysql
from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "txt"}
ALLOWED_LOGO_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.config["UPLOAD_FOLDER"] = UPLOAD_DIR


def normalize_sql(sql: str) -> str:
    return sql.replace("?", "%s")


def db_now() -> str:
    return mysql_datetime(datetime.now(UTC))


def mysql_datetime(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def positive_float(value: str) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


@app.template_filter("date_only")
def date_only(value) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    return str(value)[:10]


@app.template_filter("time_short")
def time_short(value) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%H:%M")
    text = str(value)
    return text[11:16] if len(text) >= 16 else text


def db():
    if "db" not in g:
        g.db = pymysql.connect(
            host=os.environ.get("MYSQL_HOST", "127.0.0.1"),
            port=int(os.environ.get("MYSQL_PORT", "3306")),
            user=os.environ.get("MYSQL_USER", "root"),
            password=os.environ.get("MYSQL_PASSWORD", ""),
            database=os.environ.get("MYSQL_DATABASE", "employment_platform"),
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )
    return g.db


@app.teardown_appcontext
def close_db(_: object) -> None:
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def execute(sql: str, params: tuple = ()):
    cur = db().cursor()
    cur.execute(normalize_sql(sql), params)
    db().commit()
    return cur


def fetchone(sql: str, params: tuple = ()) -> dict | None:
    cur = db().cursor()
    cur.execute(normalize_sql(sql), params)
    return cur.fetchone()


def fetchall(sql: str, params: tuple = ()) -> list[dict]:
    cur = db().cursor()
    cur.execute(normalize_sql(sql), params)
    return cur.fetchall()


def public_notification_body(body: str) -> str:
    vacancy_id = extract_vacancy_link(body)
    if vacancy_id:
        body = body.replace(f" [vacancy:{vacancy_id}]", "")
    participant_id = extract_chat_participant_link(body)
    if participant_id:
        body = body.replace(f" [chat_user:{participant_id}]", "")
    return body


def send_email(to_email: str, subject: str, body: str) -> bool:
    host = os.environ.get("SMTP_HOST", "").strip()
    if not host:
        app.logger.warning("Email notification skipped for %s: SMTP_HOST is not configured.", to_email)
        return False
    port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "")
    sender = os.environ.get("SMTP_FROM", username or "support@jobsearch.ru").strip()
    use_tls = os.environ.get("SMTP_TLS", "1") != "0"
    if username in {"ton_email@gmail.com", "votre_email@gmail.com"} or password in {"", "mot_de_passe_application"}:
        app.logger.warning(
            "Email notification skipped for %s: replace SMTP_USER/SMTP_PASSWORD placeholder values with real SMTP credentials.",
            to_email,
        )
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = to_email
    message.set_content(body)

    try:
        with smtplib.SMTP(host, port, timeout=10) as smtp:
            if use_tls:
                smtp.starttls()
            if username:
                smtp.login(username, password)
            smtp.send_message(message)
        return True
    except Exception as exc:
        app.logger.warning("Email notification was not sent: %s", exc)
        return False


def email_code_required(user: dict) -> bool:
    if user["role"] == "admin":
        return True
    if user["role"] == "employer":
        return bool(user.get("email_login_code_enabled"))
    return False


def create_login_code(user: dict) -> str:
    code = f"{secrets.randbelow(1_000_000):06d}"
    now = datetime.now(UTC)
    execute(
        "UPDATE login_codes SET used_at=? WHERE user_id=? AND used_at IS NULL",
        (mysql_datetime(now), user["id"]),
    )
    execute(
        "INSERT INTO login_codes(user_id, code_hash, expires_at, created_at) VALUES(?,?,?,?)",
        (
            user["id"],
            generate_password_hash(code),
            mysql_datetime(now + timedelta(minutes=1)),
            mysql_datetime(now),
        ),
    )
    return code


def send_login_code(user: dict, code: str) -> bool:
    subject = "Код входа JobSearch"
    body = (
        f"Ваш код входа в JobSearch: {code}\n\n"
        "Код действует 1 минуту. Если вы не входили в систему, проигнорируйте это письмо."
    )
    sent = send_email(user["email"], subject, body)
    if not sent:
        app.logger.warning("LOCAL LOGIN CODE for %s: %s", user["email"], code)
    return sent


def send_notification_email(user_id: int, title: str, body: str) -> None:
    user = fetchone("SELECT email, full_name FROM users WHERE id=?", (user_id,))
    if user and user.get("email"):
        visible_body = public_notification_body(body)
        send_email(
            user["email"],
            f"JobSearch: {title}",
            f"Здравствуйте, {user['full_name']}!\n\n{visible_body}\n\nОткройте JobSearch, чтобы ответить или посмотреть детали.",
        )


def notify_user(user_id: int, title: str, body: str) -> None:
    execute(
        "INSERT INTO notifications(user_id, title, body, created_at) VALUES(?,?,?,?)",
        (user_id, title, body, db_now()),
    )
    send_notification_email(user_id, title, body)


def notify_chat_message(user_id: int, vacancy: dict, sender_id: int) -> None:
    title = "Новое сообщение"
    body = f"Новое сообщение по вакансии «{vacancy['title']}». [vacancy:{vacancy['id']}] [chat_user:{sender_id}]"
    existing = fetchone(
        """
        SELECT id FROM notifications
        WHERE user_id=? AND title=? AND body=?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (user_id, title, body),
    )
    if existing:
        execute(
            "UPDATE notifications SET is_read=0, created_at=? WHERE id=?",
            (db_now(), existing["id"]),
        )
        execute(
            "DELETE FROM notifications WHERE user_id=? AND title=? AND body=? AND id<>?",
            (user_id, title, body, existing["id"]),
        )
        send_notification_email(user_id, title, body)
        return
    notify_user(user_id, title, body)


def extract_vacancy_link(body: str) -> int | None:
    return extract_marker_id(body, "[vacancy:")


def extract_chat_participant_link(body: str) -> int | None:
    return extract_marker_id(body, "[chat_user:")


def extract_marker_id(body: str, marker: str) -> int | None:
    if marker not in body:
        return None
    try:
        return int(body.split(marker, 1)[1].split("]", 1)[0])
    except (ValueError, IndexError):
        return None


def compact_chat_notifications(user_id: int) -> None:
    rows = fetchall(
        """
        SELECT id, title, body, is_read
        FROM notifications
        WHERE user_id=? AND title='Новое сообщение'
        ORDER BY created_at DESC, id DESC
        """,
        (user_id,),
    )
    kept_by_thread = {}
    for row in rows:
        vacancy_id = extract_vacancy_link(row["body"])
        if not vacancy_id:
            continue
        thread_key = (vacancy_id, extract_chat_participant_link(row["body"]) or 0)
        if thread_key not in kept_by_thread:
            kept_by_thread[thread_key] = row
            continue
        kept = kept_by_thread[thread_key]
        if not row["is_read"] and kept["is_read"]:
            execute("UPDATE notifications SET is_read=0 WHERE id=?", (kept["id"],))
            kept["is_read"] = 0
        execute("DELETE FROM notifications WHERE id=?", (row["id"],))


def init_db() -> None:
    UPLOAD_DIR.mkdir(exist_ok=True)
    if app.config.get("SCHEMA_EXTENSIONS_READY"):
        return
    try:
        fetchone("SELECT id FROM users LIMIT 1")
    except Exception as exc:
        raise RuntimeError(
            "MySQL database is not ready. Import database_mysql.sql in phpMyAdmin first."
        ) from exc
    try:
        execute("ALTER TABLE users ADD COLUMN email_login_code_enabled BOOLEAN NOT NULL DEFAULT FALSE")
    except pymysql.err.OperationalError:
        pass
    try:
        execute("ALTER TABLE companies ADD COLUMN description TEXT")
    except pymysql.err.OperationalError:
        pass
    try:
        execute("ALTER TABLE companies ADD COLUMN company_size VARCHAR(80)")
    except pymysql.err.OperationalError:
        pass
    for column_sql in (
        "ALTER TABLE resumes ADD COLUMN work_experience TEXT",
        "ALTER TABLE resumes ADD COLUMN education_history TEXT",
        "ALTER TABLE resumes ADD COLUMN languages TEXT",
        "ALTER TABLE resumes ADD COLUMN certificates TEXT",
        "ALTER TABLE resumes ADD COLUMN portfolio_links TEXT",
        "ALTER TABLE resumes ADD COLUMN availability_status VARCHAR(120)",
    ):
        try:
            execute(column_sql)
        except pymysql.err.OperationalError:
            pass
    execute(
        """
        CREATE TABLE IF NOT EXISTS favorites (
          id INT AUTO_INCREMENT PRIMARY KEY,
          user_id INT NOT NULL,
          item_type ENUM('vacancy', 'resume') NOT NULL,
          item_id INT NOT NULL,
          created_at DATETIME NOT NULL,
          UNIQUE KEY uq_favorite_once (user_id, item_type, item_id),
          INDEX idx_favorites_user (user_id, item_type, created_at),
          CONSTRAINT fk_favorites_user
            FOREIGN KEY (user_id) REFERENCES users(id)
            ON DELETE CASCADE
        )
        """
    )
    execute(
        """
        CREATE TABLE IF NOT EXISTS application_history (
          id INT AUTO_INCREMENT PRIMARY KEY,
          application_id INT NOT NULL,
          old_status VARCHAR(40),
          new_status VARCHAR(40) NOT NULL,
          comment VARCHAR(255),
          created_at DATETIME NOT NULL,
          CONSTRAINT fk_application_history_application
            FOREIGN KEY (application_id) REFERENCES applications(id)
            ON DELETE CASCADE,
          INDEX idx_application_history (application_id, created_at)
        )
        """
    )
    execute(
        """
        CREATE TABLE IF NOT EXISTS vacancy_views (
          id INT AUTO_INCREMENT PRIMARY KEY,
          vacancy_id INT NOT NULL,
          viewer_id INT,
          created_at DATETIME NOT NULL,
          CONSTRAINT fk_vacancy_views_vacancy
            FOREIGN KEY (vacancy_id) REFERENCES vacancies(id)
            ON DELETE CASCADE,
          INDEX idx_vacancy_views (vacancy_id, created_at)
        )
        """
    )
    execute(
        """
        CREATE TABLE IF NOT EXISTS employer_notes (
          id INT AUTO_INCREMENT PRIMARY KEY,
          employer_id INT NOT NULL,
          resume_id INT NOT NULL,
          note TEXT NOT NULL,
          created_at DATETIME NOT NULL,
          INDEX idx_employer_notes (employer_id, resume_id, created_at)
        )
        """
    )
    execute(
        """
        CREATE TABLE IF NOT EXISTS reports (
          id INT AUTO_INCREMENT PRIMARY KEY,
          reporter_id INT,
          item_type ENUM('vacancy') NOT NULL,
          item_id INT NOT NULL,
          reason VARCHAR(255) NOT NULL,
          created_at DATETIME NOT NULL,
          INDEX idx_reports (item_type, item_id, created_at)
        )
        """
    )
    execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
          id INT AUTO_INCREMENT PRIMARY KEY,
          vacancy_id INT NOT NULL,
          sender_id INT NOT NULL,
          receiver_id INT NOT NULL,
          body TEXT NOT NULL,
          is_read BOOLEAN NOT NULL DEFAULT FALSE,
          created_at DATETIME NOT NULL,
          INDEX idx_messages_receiver (receiver_id, is_read, created_at),
          INDEX idx_messages_vacancy (vacancy_id, created_at)
        )
        """
    )
    execute(
        """
        CREATE TABLE IF NOT EXISTS login_codes (
          id INT AUTO_INCREMENT PRIMARY KEY,
          user_id INT NOT NULL,
          code_hash VARCHAR(255) NOT NULL,
          expires_at DATETIME NOT NULL,
          used_at DATETIME,
          created_at DATETIME NOT NULL,
          INDEX idx_login_codes_user (user_id, expires_at, used_at)
        )
        """
    )
    app.config["SCHEMA_EXTENSIONS_READY"] = True


def current_user() -> dict | None:
    user_id = session.get("user_id")
    if not user_id:
        return None
    return fetchone("SELECT * FROM users WHERE id=?", (user_id,))


def favorite_exists(user_id: int, item_type: str, item_id: int) -> bool:
    return bool(
        fetchone(
            "SELECT id FROM favorites WHERE user_id=? AND item_type=? AND item_id=?",
            (user_id, item_type, item_id),
        )
    )


def notify_matching_applicants(vacancy_id: int) -> None:
    vacancy = fetchone(
        """
        SELECT v.*, c.name AS company_name
        FROM vacancies v
        JOIN companies c ON c.id = v.company_id
        WHERE v.id=?
        """,
        (vacancy_id,),
    )
    if not vacancy:
        return
    resumes = fetchall(
        """
        SELECT r.*, u.id AS applicant_id
        FROM resumes r
        JOIN users u ON u.id = r.user_id
        WHERE r.is_active=1
        """
    )
    vacancy_skills = split_skills(vacancy["required_skills"])
    for resume_item in resumes:
        resume_skills = split_skills(resume_item["skills"])
        same_city = resume_item["city"].lower() == vacancy["city"].lower()
        skill_hit = bool(vacancy_skills & resume_skills)
        salary_ok = float(resume_item["desired_salary"] or 0) <= float(vacancy["salary"] or 0)
        if same_city or (skill_hit and salary_ok):
            notify_user(
                resume_item["applicant_id"],
                "Новая подходящая вакансия",
                f"{vacancy['company_name']} опубликовала вакансию «{vacancy['title']}» в городе {vacancy['city']}.",
            )


@app.context_processor
def inject_globals() -> dict:
    user = current_user()
    unread_notifications = 0
    unread_messages = 0
    if user:
        row = fetchone(
            "SELECT COUNT(*) AS count FROM notifications WHERE user_id=? AND is_read=0",
            (user["id"],),
        )
        unread_notifications = row["count"] if row else 0
        row = fetchone(
            "SELECT COUNT(*) AS count FROM messages WHERE receiver_id=? AND is_read=0",
            (user["id"],),
        )
        unread_messages = row["count"] if row else 0
    return {
        "current_user": user,
        "role_names": role_names,
        "unread_notifications": unread_notifications,
        "unread_messages": unread_messages,
        "status_labels": APPLICATION_STATUS_LABELS,
    }


role_names = {
    "applicant": "Соискатель",
    "employer": "Работодатель",
    "admin": "Администратор",
}

education_scores = {
    "secondary": 0.35,
    "Среднее": 0.35,
    "college": 0.55,
    "Среднее специальное": 0.55,
    "bachelor": 0.75,
    "Бакалавриат": 0.75,
    "higher": 0.9,
    "Высшее": 0.9,
    "master": 1.0,
    "Магистратура": 1.0,
    "Аспирантура": 1.0,
    "Курсы / профессиональная переподготовка": 0.65,
}

APPLICATION_STATUS_LABELS = {
    "sent": "Отправлено",
    "viewed": "Просмотрено работодателем",
    "invited": "Приглашение",
    "rejected": "Отказ",
}

feature_labels = [
    "Уровень образования",
    "Совпадение навыков",
    "Средний уровень навыков",
    "Соответствие стажа",
    "Соответствие зарплаты",
    "Совпадение города",
]


def login_required(role: str | None = None):
    def decorator(view):
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user:
                flash("Необходимо войти в систему.", "warning")
                return redirect(url_for("login"))
            if role and user["role"] != role:
                abort(403)
            return view(*args, **kwargs)

        wrapped.__name__ = view.__name__
        return wrapped

    return decorator


def split_skills(value: str) -> set[str]:
    return {skill.strip().lower() for skill in value.split(",") if skill.strip()}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def allowed_logo(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_LOGO_EXTENSIONS


def apply_automatic_deactivation() -> None:
    now = datetime.now(UTC)
    last_run = app.config.get("AUTO_DEACTIVATION_LAST_RUN")
    if last_run and (now - last_run).total_seconds() < 60:
        return

    vacancy_limit = mysql_datetime(now - timedelta(days=30))
    resume_limit = mysql_datetime(now - timedelta(days=90))
    execute("UPDATE vacancies SET is_active=0 WHERE last_confirmed_at < ?", (vacancy_limit,))
    execute("UPDATE resumes SET is_active=0 WHERE updated_at < ?", (resume_limit,))

    stale = mysql_datetime(now - timedelta(days=10))
    rows = fetchall(
        """
        SELECT v.id
        FROM vacancies v
        JOIN applications a ON a.vacancy_id = v.id
        WHERE v.is_active=1 AND a.created_at < ?
        GROUP BY v.id
        HAVING COUNT(a.id) > 50 AND SUM(CASE WHEN a.status != 'sent' THEN 1 ELSE 0 END)=0
        """,
        (stale,),
    )
    for row in rows:
        execute("UPDATE vacancies SET needs_attention=1 WHERE id=?", (row["id"],))
    app.config["AUTO_DEACTIVATION_LAST_RUN"] = now


def resume_features(resume: dict, vacancy: dict) -> np.ndarray:
    resume_skills = split_skills(resume["skills"])
    required_skills = split_skills(vacancy["required_skills"])
    skill_match = len(resume_skills & required_skills) / max(len(required_skills), 1)
    education = education_scores.get(resume["education_level"], 0.3)
    avg_skill = min(max(float(resume["skills_level"]), 0), 1)
    experience = min(float(resume["experience_years"]) / max(float(vacancy["experience_required"]), 1), 1)
    salary_fit = 1.0 if float(resume["desired_salary"]) <= float(vacancy["salary"]) else max(float(vacancy["salary"]) / max(float(resume["desired_salary"]), 1), 0)
    city_fit = 1.0 if resume["city"].strip().lower() == vacancy["city"].strip().lower() else 0.0
    return np.array([education, skill_match, avg_skill, experience, salary_fit, city_fit], dtype=float)


def train_discriminant_model() -> tuple[np.ndarray, float, str]:
    rows = fetchall(
        """
        SELECT a.status, r.*, v.id AS vacancy_ref, v.education_required, v.experience_required,
               v.required_skills, v.salary, v.city AS vacancy_city
        FROM applications a
        JOIN resumes r ON r.user_id = a.applicant_id
        JOIN vacancies v ON v.id = a.vacancy_id
        WHERE a.status IN ('invited', 'rejected')
        """
    )
    if len(rows) < 4:
        return np.array([0.18, 0.32, 0.18, 0.16, 0.08, 0.08]), 0.52, "default"

    success, failure = [], []
    for row in rows:
        vacancy = {
            "required_skills": row["required_skills"],
            "experience_required": row["experience_required"],
            "salary": row["salary"],
            "city": row["vacancy_city"],
        }
        features = resume_features(row, vacancy)
        if row["status"] == "invited":
            success.append(features)
        else:
            failure.append(features)

    if not success or not failure:
        return np.array([0.18, 0.32, 0.18, 0.16, 0.08, 0.08]), 0.52, "default"

    success_mean = np.mean(success, axis=0)
    failure_mean = np.mean(failure, axis=0)
    weights = success_mean - failure_mean
    if np.allclose(weights, 0):
        weights = np.array([0.18, 0.32, 0.18, 0.16, 0.08, 0.08])
    threshold = float((np.dot(weights, success_mean) + np.dot(weights, failure_mean)) / 2)
    return weights, threshold, "trained"


def classify_vacancy(resume: dict, vacancy: dict, weights: np.ndarray, threshold: float) -> dict:
    features = resume_features(resume, vacancy)
    contributions = weights * features
    score = float(np.dot(weights, features))
    margin = score - threshold
    confidence = min(abs(margin) / max(abs(threshold), 0.01), 1.0)
    match_percent = int(round(float(np.mean(features)) * 100))
    # City is displayed separately as a strict binary badge, so keep the
    # explanatory factors focused on professional matching.
    professional_indexes = np.array([0, 1, 2, 3, 4])
    top_indexes = professional_indexes[np.argsort(np.abs(contributions[professional_indexes]))[::-1][:3]]
    explanation = [
        {
            "label": feature_labels[int(index)],
            "feature": round(float(features[index]), 3),
            "weight": round(float(weights[index]), 3),
            "contribution": round(float(contributions[index]), 3),
        }
        for index in top_indexes
    ]
    return {
        "score": round(score, 3),
        "recommended": score > threshold,
        "features": [round(float(x), 2) for x in features],
        "city_match": bool(features[5] == 1.0),
        "margin": round(margin, 3),
        "confidence": round(confidence, 2),
        "match_percent": max(0, min(match_percent, 100)),
        "explanation": explanation,
    }


def ranked_vacancies_for(resume: dict) -> dict:
    weights, threshold, mode = train_discriminant_model()
    vacancies = fetchall(
        """
        SELECT v.*, c.name AS company_name, c.logo AS company_logo
        FROM vacancies v
        JOIN companies c ON c.id = v.company_id
        WHERE v.is_active=1
        ORDER BY v.created_at DESC
        """
    )
    result = []
    for vacancy in vacancies:
        classification = classify_vacancy(resume, vacancy, weights, threshold)
        result.append(
            {
                "vacancy": vacancy,
                **classification,
                "mode": mode,
                "threshold": round(threshold, 3),
            }
        )
    result.sort(key=lambda item: (item["city_match"], item["score"]), reverse=True)
    execute(
        "INSERT INTO model_runs(applicant_id, weights, threshold, created_at) VALUES(?,?,?,?)",
        (resume["user_id"], ", ".join(f"{float(w):.3f}" for w in weights), threshold, db_now()),
    )
    return {
        "results": result,
        "weights": [
            {"label": label, "value": round(float(value), 3)}
            for label, value in zip(feature_labels, weights)
        ],
        "threshold": round(threshold, 3),
        "mode": mode,
    }


@app.before_request
def before_request() -> None:
    if request.endpoint in {"static", "uploaded_file"}:
        return
    init_db()
    apply_automatic_deactivation()


@app.route("/")
def index():
    vacancies = fetchall(
        """
        SELECT v.*, c.name AS company_name, c.logo AS company_logo
        FROM vacancies v
        JOIN companies c ON c.id = v.company_id
        WHERE v.is_active=1
        ORDER BY v.created_at DESC
        LIMIT 8
        """
    )
    companies = fetchall(
        """
        SELECT c.id, c.name, c.logo, COUNT(v.id) AS vacancy_count
        FROM companies c
        LEFT JOIN vacancies v ON v.company_id = c.id AND v.is_active=1
        GROUP BY c.id, c.name, c.logo
        ORDER BY vacancy_count DESC, c.name ASC
        LIMIT 8
        """
    )
    return render_template("index.html", vacancies=vacancies, companies=companies)


@app.route("/companies")
def companies():
    items = fetchall(
        """
        SELECT c.id, c.name, c.logo, c.industry, c.city, c.description, c.company_size, c.is_verified,
               COUNT(v.id) AS vacancy_count
        FROM companies c
        LEFT JOIN vacancies v ON v.company_id = c.id AND v.is_active=1
        GROUP BY c.id, c.name, c.logo, c.industry, c.city, c.description, c.company_size, c.is_verified
        ORDER BY vacancy_count DESC, c.name ASC
        """
    )
    return render_template("companies.html", companies=items)


@app.route("/employers")
def employers():
    return render_template("employers.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form["full_name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        role = request.form["role"]
        email_login_code_enabled = role == "employer" and request.form.get("email_login_code_enabled") == "1"
        if role not in ("applicant", "employer"):
            abort(400)
        try:
            cur = execute(
                """
                INSERT INTO users(full_name, email, password_hash, role, email_login_code_enabled, created_at)
                VALUES(?,?,?,?,?,?)
                """,
                (full_name, email, generate_password_hash(password), role, email_login_code_enabled, db_now()),
            )
        except pymysql.err.IntegrityError:
            flash("Пользователь с таким email уже существует.", "danger")
            return redirect(url_for("register"))
        session.clear()
        session["user_id"] = cur.lastrowid
        flash("Аккаунт создан. Заполните профиль, чтобы начать работу.", "success")
        if role == "applicant":
            return redirect(url_for("resume"))
        return redirect(url_for("company"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = fetchone("SELECT * FROM users WHERE email=?", (request.form["email"].strip().lower(),))
        if user and check_password_hash(user["password_hash"], request.form["password"]):
            if email_code_required(user):
                code = create_login_code(user)
                send_login_code(user, code)
                session.clear()
                session["pending_login_user_id"] = user["id"]
                session["pending_login_email"] = user["email"]
                flash("Код входа отправлен на email. Код действует 1 минуту.", "info")
                return redirect(url_for("login_code"))
            session.clear()
            session["user_id"] = user["id"]
            flash("Вход выполнен успешно.", "success")
            return redirect(url_for("dashboard"))
        flash("Неверный email или пароль.", "danger")
    return render_template("login.html")


@app.route("/login/code", methods=["GET", "POST"])
def login_code():
    pending_user_id = session.get("pending_login_user_id")
    if not pending_user_id:
        return redirect(url_for("login"))
    user = fetchone("SELECT * FROM users WHERE id=?", (pending_user_id,))
    if not user:
        session.clear()
        return redirect(url_for("login"))
    if request.method == "POST":
        code = request.form.get("code", "").strip()
        item = fetchone(
            """
            SELECT * FROM login_codes
            WHERE user_id=? AND used_at IS NULL AND expires_at >= ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (user["id"], db_now()),
        )
        if item and check_password_hash(item["code_hash"], code):
            execute("UPDATE login_codes SET used_at=? WHERE id=?", (db_now(), item["id"]))
            session.clear()
            session["user_id"] = user["id"]
            flash("Вход выполнен успешно.", "success")
            return redirect(url_for("dashboard"))
        flash("Неверный или просроченный код.", "danger")
    return render_template("login_code.html", email=session.get("pending_login_email"))


@app.route("/login/code/resend", methods=["POST"])
def resend_login_code():
    pending_user_id = session.get("pending_login_user_id")
    if not pending_user_id:
        return redirect(url_for("login"))
    user = fetchone("SELECT * FROM users WHERE id=?", (pending_user_id,))
    if not user:
        session.clear()
        return redirect(url_for("login"))
    code = create_login_code(user)
    send_login_code(user, code)
    flash("Новый код отправлен. Код действует 1 минуту.", "info")
    return redirect(url_for("login_code"))


@app.route("/logout")
def logout():
    session.clear()
    flash("Вы вышли из системы.", "info")
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required()
def dashboard():
    user = current_user()
    if user["role"] == "applicant":
        resume = fetchone("SELECT * FROM resumes WHERE user_id=?", (user["id"],))
        applications = fetchall(
            """
            SELECT a.*, v.title, c.name AS company_name,
                   (
                     SELECT GROUP_CONCAT(CONCAT(h.new_status, ':', h.created_at) ORDER BY h.created_at SEPARATOR ' | ')
                     FROM application_history h
                     WHERE h.application_id = a.id
                   ) AS status_history
            FROM applications a
            JOIN vacancies v ON v.id = a.vacancy_id
            JOIN companies c ON c.id = v.company_id
            WHERE a.applicant_id=?
            ORDER BY a.updated_at DESC
            """,
            (user["id"],),
        )
        notifications = fetchall(
            "SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 6",
            (user["id"],),
        )
        return render_template(
            "dashboard_applicant.html",
            resume=resume,
            applications=applications,
            notifications=notifications,
        )
    if user["role"] == "employer":
        company = fetchone("SELECT * FROM companies WHERE owner_id=?", (user["id"],))
        vacancies = []
        responses = []
        recommended_candidates = []
        employer_stats = {"vacancies": 0, "views": 0, "applications": 0, "invited": 0}
        if company:
            vacancies = fetchall(
                """
                SELECT v.*,
                       COUNT(DISTINCT vv.id) AS view_count,
                       COUNT(DISTINCT a.id) AS application_count,
                       SUM(CASE WHEN a.status='invited' THEN 1 ELSE 0 END) AS invited_count,
                       SUM(CASE WHEN a.status='rejected' THEN 1 ELSE 0 END) AS rejected_count
                FROM vacancies v
                LEFT JOIN vacancy_views vv ON vv.vacancy_id = v.id
                LEFT JOIN applications a ON a.vacancy_id = v.id
                WHERE v.company_id=?
                GROUP BY v.id
                ORDER BY v.created_at DESC
                """,
                (company["id"],),
            )
            responses = fetchall(
                """
                SELECT a.*, v.title, u.full_name, r.city, r.experience_years, r.skills
                FROM applications a
                JOIN vacancies v ON v.id = a.vacancy_id
                JOIN users u ON u.id = a.applicant_id
                LEFT JOIN resumes r ON r.user_id = u.id
                WHERE v.company_id=?
                ORDER BY a.updated_at DESC
                """,
                (company["id"],),
            )
            employer_stats = {
                "vacancies": len(vacancies),
                "views": sum(int(v["view_count"] or 0) for v in vacancies),
                "applications": sum(int(v["application_count"] or 0) for v in vacancies),
                "invited": sum(int(v["invited_count"] or 0) for v in vacancies),
            }
            resumes = fetchall(
                """
                SELECT r.*, u.full_name, u.email
                FROM resumes r
                JOIN users u ON u.id = r.user_id
                WHERE r.is_active=1
                ORDER BY r.updated_at DESC
                LIMIT 40
                """
            )
            scored = []
            for vacancy in vacancies[:5]:
                for resume_item in resumes:
                    score = float(np.dot(train_discriminant_model()[0], resume_features(resume_item, vacancy)))
                    scored.append(
                        {
                            "resume": resume_item,
                            "vacancy": vacancy,
                            "score": round(score * 100, 1),
                        }
                    )
            recommended_candidates = sorted(scored, key=lambda item: item["score"], reverse=True)[:8]
        return render_template(
            "dashboard_employer.html",
            company=company,
            vacancies=vacancies,
            responses=responses,
            employer_stats=employer_stats,
            recommended_candidates=recommended_candidates,
        )
    return redirect(url_for("admin"))


@app.route("/resume", methods=["GET", "POST"])
@login_required("applicant")
def resume():
    user = current_user()
    item = fetchone("SELECT * FROM resumes WHERE user_id=?", (user["id"],))
    if request.method == "POST":
        skills_level = float(request.form.get("skills_level", 0))
        experience_years = float(request.form.get("experience_years", 0))
        if not 0 <= skills_level <= 1 or experience_years < 0:
            flash("Проверьте числовые значения: уровень навыков должен быть от 0 до 1.", "danger")
            return redirect(url_for("resume"))

        data = (
            request.form["gender"],
            request.form.get("birth_date") or None,
            request.form["city"].strip(),
            request.form["phone"].strip(),
            request.form["education_level"],
            request.form["specialty"].strip(),
            experience_years,
            request.form["desired_position"].strip(),
            float(request.form.get("desired_salary", 0)),
            request.form["skills"].strip(),
            skills_level,
            request.form.get("work_experience", "").strip(),
            request.form.get("education_history", "").strip(),
            request.form.get("languages", "").strip(),
            request.form.get("certificates", "").strip(),
            request.form.get("portfolio_links", "").strip(),
            request.form.get("availability_status", "").strip(),
            1,
            db_now(),
            user["id"],
        )
        if item:
            execute(
                """
                UPDATE resumes SET gender=?, birth_date=?, city=?, phone=?, education_level=?,
                specialty=?, experience_years=?, desired_position=?, desired_salary=?, skills=?,
                skills_level=?, work_experience=?, education_history=?, languages=?, certificates=?,
                portfolio_links=?, availability_status=?, is_active=?, updated_at=? WHERE user_id=?
                """,
                data,
            )
        else:
            execute(
                """
                INSERT INTO resumes(gender, birth_date, city, phone, education_level, specialty,
                experience_years, desired_position, desired_salary, skills, skills_level,
                work_experience, education_history, languages, certificates, portfolio_links,
                availability_status, is_active, updated_at, user_id)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                data,
            )
        flash("Резюме сохранено и подтверждено как актуальное.", "success")
        return redirect(url_for("dashboard"))
    return render_template("resume_form.html", resume=item)


@app.route("/company", methods=["GET", "POST"])
@login_required("employer")
def company():
    user = current_user()
    item = fetchone("SELECT * FROM companies WHERE owner_id=?", (user["id"],))
    if request.method == "POST":
        logo = item["logo"] if item else None
        file = request.files.get("logo")
        if file and file.filename and allowed_logo(file.filename):
            filename = secure_filename(file.filename)
            logo = f"company_{user['id']}_{filename}"
            file.save(UPLOAD_DIR / logo)
        data = (
            request.form["name"].strip(),
            request.form["inn"].strip(),
            request.form["industry"].strip(),
            request.form["city"].strip(),
            request.form["contacts"].strip(),
            request.form.get("description", "").strip(),
            request.form.get("company_size", "").strip(),
            logo,
            db_now(),
            user["id"],
        )
        if item:
            execute(
                "UPDATE companies SET name=?, inn=?, industry=?, city=?, contacts=?, description=?, company_size=?, logo=? WHERE owner_id=?",
                data[:8] + (user["id"],),
            )
        else:
            execute(
                """
                INSERT INTO companies(name, inn, industry, city, contacts, description, company_size, logo, created_at, owner_id)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                data,
            )
        flash("Данные компании сохранены. Администратор должен подтвердить компанию.", "success")
        return redirect(url_for("dashboard"))
    return render_template("company_form.html", company=item)


@app.route("/vacancies")
def vacancies():
    filters = {
        "query": request.args.get("query", "").strip(),
        "city": request.args.get("city", "").strip(),
        "employment_type": request.args.get("employment_type", "").strip(),
        "workplace": request.args.get("workplace", "").strip(),
        "education": request.args.get("education", "").strip(),
        "experience": request.args.get("experience", "").strip(),
        "salary": request.args.get("salary", "").strip(),
        "salary_max": request.args.get("salary_max", "").strip(),
        "published": request.args.get("published", "").strip(),
        "sort": request.args.get("sort", "new").strip(),
        "with_salary": request.args.get("with_salary", "").strip(),
        "verified": request.args.get("verified", "").strip(),
    }
    sql = """
        SELECT v.*, c.name AS company_name, c.logo AS company_logo
        FROM vacancies v
        JOIN companies c ON c.id = v.company_id
        WHERE v.is_active=1
    """
    params: list = []
    if filters["query"]:
        sql += " AND (LOWER(v.title) LIKE ? OR LOWER(c.name) LIKE ? OR LOWER(v.required_skills) LIKE ?)"
        term = f"%{filters['query'].lower()}%"
        params.extend([term, term, term])
    if filters["city"]:
        sql += " AND LOWER(v.city) LIKE ?"
        params.append(f"%{filters['city'].lower()}%")
    if filters["employment_type"]:
        sql += " AND LOWER(v.employment_type) LIKE ?"
        params.append(f"%{filters['employment_type'].lower()}%")
    if filters["workplace"]:
        sql += " AND LOWER(v.workplace) LIKE ?"
        params.append(f"%{filters['workplace'].lower()}%")
    if filters["education"]:
        sql += " AND LOWER(v.education_required) LIKE ?"
        params.append(f"%{filters['education'].lower()}%")
    experience = positive_float(filters["experience"])
    salary_min = positive_float(filters["salary"])
    salary_max = positive_float(filters["salary_max"])
    if experience is not None:
        sql += " AND v.experience_required<=?"
        params.append(experience)
    if salary_min is not None:
        sql += " AND v.salary>=?"
        params.append(salary_min)
    if salary_max is not None:
        sql += " AND v.salary<=?"
        params.append(salary_max)
    if filters["with_salary"]:
        sql += " AND v.salary>0"
    if filters["verified"]:
        sql += " AND c.is_verified=1"
    published_days = {"today": 1, "3days": 3, "week": 7, "month": 30}
    if filters["published"] in published_days:
        date_from = datetime.now(UTC) - timedelta(days=published_days[filters["published"]])
        sql += " AND v.created_at>=?"
        params.append(mysql_datetime(date_from))
    sort_sql = {
        "new": "v.created_at DESC",
        "salary_desc": "v.salary DESC, v.created_at DESC",
        "salary_asc": "v.salary ASC, v.created_at DESC",
        "relevance": "v.salary DESC, v.created_at DESC",
    }
    sql += f" ORDER BY {sort_sql.get(filters['sort'], sort_sql['new'])}"
    return render_template("vacancies.html", vacancies=fetchall(sql, tuple(params)), filters=filters)


@app.route("/vacancy/<int:vacancy_id>")
def vacancy_detail(vacancy_id: int):
    vacancy = fetchone(
        """
        SELECT v.*, c.name AS company_name, c.contacts, c.logo AS company_logo
        FROM vacancies v
        JOIN companies c ON c.id = v.company_id
        WHERE v.id=?
        """,
        (vacancy_id,),
    )
    if not vacancy:
        abort(404)
    application = None
    user = current_user()
    execute(
        "INSERT INTO vacancy_views(vacancy_id, viewer_id, created_at) VALUES(?,?,?)",
        (vacancy_id, user["id"] if user else None, db_now()),
    )
    if user and user["role"] == "applicant":
        application = fetchone(
            "SELECT * FROM applications WHERE vacancy_id=? AND applicant_id=?",
            (vacancy_id, user["id"]),
        )
    is_favorite = bool(user and user["role"] == "applicant" and favorite_exists(user["id"], "vacancy", vacancy_id))
    return render_template(
        "vacancy_detail.html",
        vacancy=vacancy,
        application=application,
        is_favorite=is_favorite,
    )


@app.route("/companies/<int:company_id>")
def company_public(company_id: int):
    company = fetchone(
        """
        SELECT c.*, COUNT(v.id) AS vacancy_count
        FROM companies c
        LEFT JOIN vacancies v ON v.company_id = c.id AND v.is_active=1
        WHERE c.id=?
        GROUP BY c.id
        """,
        (company_id,),
    )
    if not company:
        abort(404)
    vacancies = fetchall(
        """
        SELECT v.*, c.name AS company_name, c.logo AS company_logo
        FROM vacancies v
        JOIN companies c ON c.id = v.company_id
        WHERE v.company_id=? AND v.is_active=1
        ORDER BY v.created_at DESC
        """,
        (company_id,),
    )
    return render_template("company_public.html", company=company, vacancies=vacancies)


@app.route("/security")
def security():
    return render_template("security.html")


@app.route("/career")
def career():
    return render_template("career.html")


@app.route("/market")
def market():
    salary_by_specialty = fetchall(
        """
        SELECT title AS label, ROUND(AVG(salary), 0) AS value
        FROM vacancies
        WHERE salary > 0 AND is_active=1
        GROUP BY title
        ORDER BY value DESC
        LIMIT 8
        """
    )
    vacancies_by_city = fetchall(
        """
        SELECT city AS label, COUNT(*) AS value
        FROM vacancies
        WHERE is_active=1
        GROUP BY city
        ORDER BY value DESC
        LIMIT 8
        """
    )
    sectors = fetchall(
        """
        SELECT c.industry AS label, COUNT(v.id) AS value
        FROM companies c
        LEFT JOIN vacancies v ON v.company_id = c.id AND v.is_active=1
        GROUP BY c.industry
        ORDER BY value DESC
        LIMIT 8
        """
    )
    vacancy_count = fetchone("SELECT COUNT(*) AS count FROM vacancies WHERE is_active=1")["count"]
    resume_count = fetchone("SELECT COUNT(*) AS count FROM resumes WHERE is_active=1")["count"]
    ratio = round(float(resume_count) / max(float(vacancy_count), 1), 2)
    return render_template(
        "market.html",
        salary_by_specialty=salary_by_specialty,
        vacancies_by_city=vacancies_by_city,
        sectors=sectors,
        vacancy_count=vacancy_count,
        resume_count=resume_count,
        ratio=ratio,
    )


@app.route("/favorites")
@login_required()
def favorites():
    user = current_user()
    if user["role"] == "applicant":
        items = fetchall(
            """
            SELECT f.id AS favorite_id, f.created_at AS favorite_created_at,
                   v.*, c.name AS company_name, c.logo AS company_logo
            FROM favorites f
            JOIN vacancies v ON v.id = f.item_id
            JOIN companies c ON c.id = v.company_id
            WHERE f.user_id=? AND f.item_type='vacancy'
            ORDER BY f.created_at DESC
            """,
            (user["id"],),
        )
        return render_template("favorites.html", items=items, kind="vacancy")
    if user["role"] == "employer":
        items = fetchall(
            """
            SELECT f.id AS favorite_id, f.created_at AS favorite_created_at,
                   r.*, u.full_name, u.email
            FROM favorites f
            JOIN resumes r ON r.id = f.item_id
            JOIN users u ON u.id = r.user_id
            WHERE f.user_id=? AND f.item_type='resume'
            ORDER BY f.created_at DESC
            """,
            (user["id"],),
        )
        return render_template("favorites.html", items=items, kind="resume")
    return redirect(url_for("admin"))


@app.route("/favorites/<item_type>/<int:item_id>/toggle", methods=["POST"])
@login_required()
def toggle_favorite(item_type: str, item_id: int):
    user = current_user()
    allowed = (user["role"] == "applicant" and item_type == "vacancy") or (
        user["role"] == "employer" and item_type == "resume"
    )
    if not allowed:
        abort(403)
    existing = fetchone(
        "SELECT id FROM favorites WHERE user_id=? AND item_type=? AND item_id=?",
        (user["id"], item_type, item_id),
    )
    if existing:
        execute("DELETE FROM favorites WHERE id=?", (existing["id"],))
        flash("Удалено из избранного.", "success")
    else:
        execute(
            "INSERT INTO favorites(user_id, item_type, item_id, created_at) VALUES(?,?,?,?)",
            (user["id"], item_type, item_id, db_now()),
        )
        flash("Добавлено в избранное.", "success")
    next_url = request.form.get("next") or url_for("favorites")
    return redirect(next_url)


@app.route("/vacancy/new", methods=["GET", "POST"])
@login_required("employer")
def vacancy_form():
    user = current_user()
    company = fetchone("SELECT * FROM companies WHERE owner_id=?", (user["id"],))
    if not company:
        flash("Сначала заполните профиль компании.", "warning")
        return redirect(url_for("company"))
    if request.method == "POST":
        now = db_now()
        cur = execute(
            """
            INSERT INTO vacancies(company_id, title, city, workplace, education_required,
            experience_required, duties, conditions, salary, employment_type, required_skills,
            is_active, needs_attention, created_at, last_confirmed_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                company["id"],
                request.form["title"].strip(),
                request.form["city"].strip(),
                request.form["workplace"].strip(),
                request.form["education_required"],
                float(request.form.get("experience_required", 0)),
                request.form["duties"].strip(),
                request.form["conditions"].strip(),
                float(request.form.get("salary", 0)),
                request.form["employment_type"],
                request.form["required_skills"].strip(),
                1,
                0 if company["is_verified"] else 1,
                now,
                now,
            ),
        )
        if not company["is_verified"]:
            admin = fetchone("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1")
            if admin:
                notify_user(
                    admin["id"],
                    "Новая вакансия от компании на проверке",
                    f"Компания «{company['name']}» опубликовала вакансию «{request.form['title'].strip()}». Профиль компании ожидает проверки.",
                )
        notify_matching_applicants(cur.lastrowid)
        flash("Вакансия опубликована. Профиль компании будет проверен администратором отдельно.", "success")
        return redirect(url_for("dashboard"))
    return render_template("vacancy_form.html")


@app.route("/vacancy/<int:vacancy_id>/apply", methods=["POST"])
@login_required("applicant")
def apply(vacancy_id: int):
    user = current_user()
    resume = fetchone("SELECT * FROM resumes WHERE user_id=? AND is_active=1", (user["id"],))
    vacancy = fetchone("SELECT * FROM vacancies WHERE id=? AND is_active=1", (vacancy_id,))
    if not resume:
        flash("Сначала заполните активное резюме.", "warning")
        return redirect(url_for("resume"))
    if not vacancy:
        abort(404)
    score = float(np.dot(train_discriminant_model()[0], resume_features(resume, vacancy)))
    try:
        now = db_now()
        cur = execute(
            """
            INSERT INTO applications(vacancy_id, applicant_id, status, score, created_at, updated_at)
            VALUES(?,?,?,?,?,?)
            """,
            (vacancy_id, user["id"], "sent", score, now, now),
        )
        execute(
            """
            INSERT INTO application_history(application_id, old_status, new_status, comment, created_at)
            VALUES(?,?,?,?,?)
            """,
            (cur.lastrowid, None, "sent", "Кандидат отправил отклик.", now),
        )
        flash("Отклик отправлен работодателю.", "success")
    except pymysql.err.IntegrityError:
        flash("Вы уже откликались на эту вакансию.", "info")
    return redirect(url_for("vacancy_detail", vacancy_id=vacancy_id))


@app.route("/vacancy/<int:vacancy_id>/report", methods=["POST"])
@login_required()
def report_vacancy(vacancy_id: int):
    user = current_user()
    reason = request.form.get("reason", "").strip() or "Пользователь отметил вакансию как подозрительную."
    vacancy = fetchone("SELECT id, title FROM vacancies WHERE id=?", (vacancy_id,))
    if not vacancy:
        abort(404)
    execute(
        "INSERT INTO reports(reporter_id, item_type, item_id, reason, created_at) VALUES(?,?,?,?,?)",
        (user["id"], "vacancy", vacancy_id, reason, db_now()),
    )
    admin = fetchone("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1")
    if admin:
        notify_user(admin["id"], "Жалоба на вакансию", f"Поступила жалоба на вакансию «{vacancy['title']}»: {reason}")
    flash("Спасибо. Жалоба отправлена на проверку.", "success")
    return redirect(url_for("vacancy_detail", vacancy_id=vacancy_id))


def message_conversations(user: dict, search: str = "") -> list[dict]:
    if user["role"] == "applicant":
        rows = fetchall(
            """
            SELECT
              v.id AS vacancy_id,
              v.title AS vacancy_title,
              v.city AS vacancy_city,
              c.name AS company_name,
              c.logo AS company_logo,
              c.owner_id AS participant_id,
              c.name AS participant_name,
              'employer' AS participant_role,
              a.status AS application_status,
              a.created_at AS application_created_at,
              a.updated_at AS application_updated_at,
              (
                SELECT m.body
                FROM messages m
                WHERE m.vacancy_id=v.id
                  AND ((m.sender_id=? AND m.receiver_id=c.owner_id) OR (m.sender_id=c.owner_id AND m.receiver_id=?))
                ORDER BY m.created_at DESC
                LIMIT 1
              ) AS last_body,
              (
                SELECT m.created_at
                FROM messages m
                WHERE m.vacancy_id=v.id
                  AND ((m.sender_id=? AND m.receiver_id=c.owner_id) OR (m.sender_id=c.owner_id AND m.receiver_id=?))
                ORDER BY m.created_at DESC
                LIMIT 1
              ) AS last_message_at,
              (
                SELECT COUNT(*)
                FROM messages m
                WHERE m.vacancy_id=v.id AND m.receiver_id=? AND m.sender_id=c.owner_id AND m.is_read=0
              ) AS unread_count
            FROM applications a
            JOIN vacancies v ON v.id = a.vacancy_id
            JOIN companies c ON c.id = v.company_id
            WHERE a.applicant_id=?
            ORDER BY COALESCE(last_message_at, a.updated_at, a.created_at) DESC
            """,
            (user["id"], user["id"], user["id"], user["id"], user["id"], user["id"]),
        )
    elif user["role"] == "employer":
        rows = fetchall(
            """
            SELECT
              v.id AS vacancy_id,
              v.title AS vacancy_title,
              v.city AS vacancy_city,
              c.name AS company_name,
              c.logo AS company_logo,
              u.id AS participant_id,
              u.full_name AS participant_name,
              'applicant' AS participant_role,
              r.city AS applicant_city,
              a.status AS application_status,
              a.created_at AS application_created_at,
              a.updated_at AS application_updated_at,
              (
                SELECT m.body
                FROM messages m
                WHERE m.vacancy_id=v.id
                  AND ((m.sender_id=? AND m.receiver_id=u.id) OR (m.sender_id=u.id AND m.receiver_id=?))
                ORDER BY m.created_at DESC
                LIMIT 1
              ) AS last_body,
              (
                SELECT m.created_at
                FROM messages m
                WHERE m.vacancy_id=v.id
                  AND ((m.sender_id=? AND m.receiver_id=u.id) OR (m.sender_id=u.id AND m.receiver_id=?))
                ORDER BY m.created_at DESC
                LIMIT 1
              ) AS last_message_at,
              (
                SELECT COUNT(*)
                FROM messages m
                WHERE m.vacancy_id=v.id AND m.receiver_id=? AND m.sender_id=u.id AND m.is_read=0
              ) AS unread_count
            FROM applications a
            JOIN vacancies v ON v.id = a.vacancy_id
            JOIN companies c ON c.id = v.company_id
            JOIN users u ON u.id = a.applicant_id
            LEFT JOIN resumes r ON r.user_id = u.id
            WHERE c.owner_id=?
            ORDER BY COALESCE(last_message_at, a.updated_at, a.created_at) DESC
            """,
            (user["id"], user["id"], user["id"], user["id"], user["id"], user["id"]),
        )
    else:
        rows = []

    for row in rows:
        row["last_activity"] = row.get("last_message_at") or row.get("application_updated_at") or row.get("application_created_at")
        row["last_body"] = row.get("last_body") or "Отклик по вакансии"
        row["unread_count"] = int(row.get("unread_count") or 0)

    query = search.strip().lower()
    if query:
        rows = [
            row for row in rows
            if query in " ".join(
                str(row.get(key) or "").lower()
                for key in ("participant_name", "vacancy_title", "company_name", "vacancy_city", "applicant_city")
            )
        ]
    return rows


def selected_message_conversation(conversations: list[dict], vacancy_id: int | None, participant_id: int | None) -> dict | None:
    if vacancy_id and participant_id:
        for row in conversations:
            if int(row["vacancy_id"]) == vacancy_id and int(row["participant_id"]) == participant_id:
                return row
    if vacancy_id:
        for row in conversations:
            if int(row["vacancy_id"]) == vacancy_id:
                return row
    return conversations[0] if conversations else None


def render_message_inbox(preselected_vacancy_id: int | None = None):
    user = current_user()
    query = request.args.get("query", "").strip()
    conversations = message_conversations(user, query)
    vacancy_id = request.values.get("vacancy_id", type=int) or request.values.get("vacancy", type=int) or preselected_vacancy_id
    participant_id = request.values.get("participant_id", type=int) or request.values.get("participant", type=int)
    selected = selected_message_conversation(conversations, vacancy_id, participant_id)

    if request.method == "POST":
        body = request.form.get("body", "").strip()
        if body and selected:
            execute(
                "INSERT INTO messages(vacancy_id, sender_id, receiver_id, body, created_at) VALUES(?,?,?,?,?)",
                (selected["vacancy_id"], user["id"], selected["participant_id"], body, db_now()),
            )
            vacancy = fetchone(
                """
                SELECT v.*, c.name AS company_name
                FROM vacancies v
                JOIN companies c ON c.id = v.company_id
                WHERE v.id=?
                """,
                (selected["vacancy_id"],),
            )
            if vacancy:
                notify_chat_message(selected["participant_id"], vacancy, user["id"])
        return redirect(url_for("message_inbox", vacancy=selected["vacancy_id"], participant=selected["participant_id"]) if selected else url_for("message_inbox"))

    thread = []
    if selected:
        execute(
            "UPDATE messages SET is_read=1 WHERE vacancy_id=? AND receiver_id=? AND sender_id=?",
            (selected["vacancy_id"], user["id"], selected["participant_id"]),
        )
        selected["unread_count"] = 0
        thread = fetchall(
            """
            SELECT m.*, sender.full_name AS sender_name, receiver.full_name AS receiver_name
            FROM messages m
            JOIN users sender ON sender.id = m.sender_id
            JOIN users receiver ON receiver.id = m.receiver_id
            WHERE m.vacancy_id=?
              AND (
                (m.sender_id=? AND m.receiver_id=?)
                OR (m.sender_id=? AND m.receiver_id=?)
              )
            ORDER BY m.created_at
            """,
            (selected["vacancy_id"], user["id"], selected["participant_id"], selected["participant_id"], user["id"]),
        )
    return render_template(
        "messages.html",
        conversations=conversations,
        selected_conversation=selected,
        messages=thread,
        query=query,
    )


@app.route("/messages", methods=["GET", "POST"])
@login_required()
def message_inbox():
    return render_message_inbox()


@app.route("/messages/vacancy/<int:vacancy_id>", methods=["GET", "POST"])
@login_required()
def vacancy_messages(vacancy_id: int):
    return render_message_inbox(vacancy_id)


@app.route("/applications/<int:application_id>/status", methods=["POST"])
@login_required("employer")
def update_application_status(application_id: int):
    user = current_user()
    company = fetchone("SELECT * FROM companies WHERE owner_id=?", (user["id"],))
    application = fetchone(
        """
        SELECT a.*, v.title
        FROM applications a
        JOIN vacancies v ON v.id = a.vacancy_id
        WHERE a.id=? AND v.company_id=?
        """,
        (application_id, company["id"] if company else 0),
    )
    if not application:
        abort(404)
    old_status = application["status"]
    status = request.form["status"]
    if status not in ("viewed", "invited", "rejected"):
        abort(400)
    reason = request.form.get("reason", "").strip()
    execute(
        "UPDATE applications SET status=?, reason=?, updated_at=? WHERE id=?",
        (status, reason, db_now(), application_id),
    )
    execute(
        """
        INSERT INTO application_history(application_id, old_status, new_status, comment, created_at)
        VALUES(?,?,?,?,?)
        """,
        (application_id, old_status, status, reason, db_now()),
    )
    status_titles = {
        "viewed": "Отклик просмотрен",
        "invited": "Приглашение на вакансию",
        "rejected": "Отказ по отклику",
    }
    message = f"Статус отклика на вакансию «{application['title']}» изменён."
    if reason:
        message += f" Комментарий работодателя: {reason}"
    notify_user(application["applicant_id"], status_titles[status], message)
    flash("Статус отклика обновлён.", "success")
    return redirect(url_for("dashboard"))


@app.route("/vacancy/<int:vacancy_id>/confirm", methods=["POST"])
@login_required("employer")
def confirm_vacancy(vacancy_id: int):
    user = current_user()
    company = fetchone("SELECT * FROM companies WHERE owner_id=?", (user["id"],))
    execute(
        "UPDATE vacancies SET is_active=1, needs_attention=0, last_confirmed_at=? WHERE id=? AND company_id=?",
        (db_now(), vacancy_id, company["id"] if company else 0),
    )
    flash("Актуальность вакансии подтверждена на 30 дней.", "success")
    return redirect(url_for("dashboard"))


@app.route("/recommendations")
@login_required("applicant")
def recommendations():
    user = current_user()
    resume = fetchone("SELECT * FROM resumes WHERE user_id=? AND is_active=1", (user["id"],))
    if not resume:
        flash("Для подбора вакансий нужно активное резюме.", "warning")
        return redirect(url_for("resume"))
    model = ranked_vacancies_for(resume)
    return render_template("recommendations.html", model=model, results=model["results"])


@app.route("/resumes")
@login_required("employer")
def resumes():
    query = request.args.get("skills", "").strip().lower()
    sql = """
        SELECT r.*, u.full_name, u.email
        FROM resumes r
        JOIN users u ON u.id = r.user_id
        WHERE r.is_active=1
    """
    params: list = []
    if query:
        sql += " AND LOWER(r.skills) LIKE ?"
        params.append(f"%{query}%")
    sql += " ORDER BY r.updated_at DESC"
    return render_template("resumes.html", resumes=fetchall(sql, tuple(params)), query=query)


@app.route("/resume/<int:resume_id>/view")
@login_required()
def resume_detail(resume_id: int):
    user = current_user()
    if user["role"] not in ("employer", "admin"):
        abort(403)
    resume = fetchone(
        """
        SELECT r.*, u.full_name, u.email
        FROM resumes r
        JOIN users u ON u.id = r.user_id
        WHERE r.id=?
        """,
        (resume_id,),
    )
    if not resume:
        abort(404)
    user = current_user()
    is_favorite = bool(user and user["role"] == "employer" and favorite_exists(user["id"], "resume", resume_id))
    notes = []
    if user and user["role"] == "employer":
        notes = fetchall(
            "SELECT * FROM employer_notes WHERE employer_id=? AND resume_id=? ORDER BY created_at DESC",
            (user["id"], resume_id),
        )
    return render_template("resume_detail.html", resume=resume, is_favorite=is_favorite, notes=notes)


@app.route("/resume/<int:resume_id>/note", methods=["POST"])
@login_required("employer")
def add_resume_note(resume_id: int):
    user = current_user()
    resume = fetchone("SELECT id FROM resumes WHERE id=? AND is_active=1", (resume_id,))
    if not resume:
        abort(404)
    note = request.form.get("note", "").strip()
    if note:
        execute(
            "INSERT INTO employer_notes(employer_id, resume_id, note, created_at) VALUES(?,?,?,?)",
            (user["id"], resume_id, note, db_now()),
        )
        flash("Заметка сохранена.", "success")
    return redirect(url_for("resume_detail", resume_id=resume_id))


@app.route("/uploads/<path:filename>")
def uploaded_file(filename: str):
    return send_from_directory(UPLOAD_DIR, filename)


@app.route("/notifications")
@login_required()
def notifications():
    user = current_user()
    compact_chat_notifications(user["id"])
    items = fetchall(
        "SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC",
        (user["id"],),
    )
    for item in items:
        vacancy_id = extract_vacancy_link(item["body"])
        participant_id = extract_chat_participant_link(item["body"])
        if not vacancy_id and item["title"] == "Новое сообщение":
            vacancy = fetchone(
                "SELECT id FROM vacancies WHERE INSTR(?, title) > 0 ORDER BY created_at DESC LIMIT 1",
                (item["body"],),
            )
            vacancy_id = vacancy["id"] if vacancy else None
        item["vacancy_id"] = vacancy_id
        item["participant_id"] = participant_id
        if vacancy_id:
            item["body"] = item["body"].replace(f" [vacancy:{vacancy_id}]", "")
        if participant_id:
            item["body"] = item["body"].replace(f" [chat_user:{participant_id}]", "")
    return render_template("notifications.html", notifications=items)


@app.route("/notifications/<int:notification_id>/read", methods=["POST"])
@login_required()
def notification_read(notification_id: int):
    user = current_user()
    item = fetchone("SELECT * FROM notifications WHERE id=? AND user_id=?", (notification_id, user["id"]))
    execute(
        "UPDATE notifications SET is_read=1 WHERE id=? AND user_id=?",
        (notification_id, user["id"]),
    )
    if item:
        vacancy_id = extract_vacancy_link(item["body"])
        participant_id = extract_chat_participant_link(item["body"])
        if vacancy_id:
            if participant_id:
                return redirect(url_for("vacancy_messages", vacancy_id=vacancy_id, participant=participant_id))
            return redirect(url_for("vacancy_messages", vacancy_id=vacancy_id))
    return redirect(url_for("notifications"))


@app.route("/admin")
@login_required("admin")
def admin():
    companies = fetchall("SELECT c.*, u.email FROM companies c JOIN users u ON u.id = c.owner_id ORDER BY c.created_at DESC")
    stats = {
        "users": fetchone("SELECT COUNT(*) AS count FROM users")["count"],
        "companies": fetchone("SELECT COUNT(*) AS count FROM companies")["count"],
        "active_vacancies": fetchone("SELECT COUNT(*) AS count FROM vacancies WHERE is_active=1")["count"],
        "resumes": fetchone("SELECT COUNT(*) AS count FROM resumes")["count"],
        "active_resumes": fetchone("SELECT COUNT(*) AS count FROM resumes WHERE is_active=1")["count"],
        "attention": fetchone("SELECT COUNT(*) AS count FROM vacancies WHERE needs_attention=1")["count"],
    }
    flagged = fetchall(
        """
        SELECT v.*, c.name AS company_name, c.logo AS company_logo
        FROM vacancies v
        JOIN companies c ON c.id = v.company_id
        WHERE v.needs_attention=1 OR v.is_active=0
        ORDER BY v.created_at DESC
        """
    )
    all_vacancies = fetchall(
        """
        SELECT v.*, c.name AS company_name, c.logo AS company_logo
        FROM vacancies v
        JOIN companies c ON c.id = v.company_id
        ORDER BY v.created_at DESC
        """
    )
    resumes_for_admin = fetchall(
        """
        SELECT r.*, u.full_name, u.email
        FROM resumes r
        JOIN users u ON u.id = r.user_id
        ORDER BY r.updated_at DESC
        """
    )
    return render_template(
        "admin.html",
        companies=companies,
        stats=stats,
        flagged=flagged,
        all_vacancies=all_vacancies,
        resumes=resumes_for_admin,
    )


@app.route("/admin/db-status")
@login_required("admin")
def admin_db_status():
    user_count = fetchone("SELECT COUNT(*) AS count FROM users")["count"]
    vacancy_count = fetchone("SELECT COUNT(*) AS count FROM vacancies")["count"]
    resume_count = fetchone("SELECT COUNT(*) AS count FROM resumes")["count"]
    return render_template(
        "db_status.html",
        engine="MySQL",
        database=os.environ.get("MYSQL_DATABASE", "employment_platform"),
        user_count=user_count,
        vacancy_count=vacancy_count,
        resume_count=resume_count,
    )


@app.route("/admin/company/<int:company_id>/verify", methods=["POST"])
@login_required("admin")
def verify_company(company_id: int):
    company = fetchone(
        """
        SELECT c.*, u.id AS owner_user_id
        FROM companies c
        JOIN users u ON u.id = c.owner_id
        WHERE c.id=?
        """,
        (company_id,),
    )
    if not company:
        abort(404)
    execute("UPDATE companies SET is_verified=1 WHERE id=?", (company_id,))
    if not company["is_verified"]:
        notify_user(
            company["owner_user_id"],
            "Компания подтверждена",
            f"Профиль компании «{company['name']}» проверен администратором. Вакансии компании отображаются с повышенным уровнем доверия.",
        )
    flash("Компания подтверждена.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/vacancy/<int:vacancy_id>/activate", methods=["POST"])
@login_required("admin")
def activate_vacancy(vacancy_id: int):
    execute(
        "UPDATE vacancies SET is_active=1, needs_attention=0, last_confirmed_at=? WHERE id=?",
        (db_now(), vacancy_id),
    )
    flash("Вакансия активирована.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/vacancy/<int:vacancy_id>/status", methods=["POST"])
@login_required("admin")
def admin_vacancy_status(vacancy_id: int):
    is_active = 1 if request.form.get("is_active") == "1" else 0
    execute(
        "UPDATE vacancies SET is_active=?, needs_attention=0, last_confirmed_at=? WHERE id=?",
        (is_active, db_now(), vacancy_id),
    )
    flash("Статус вакансии обновлён.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/resume/<int:resume_id>/status", methods=["POST"])
@login_required("admin")
def admin_resume_status(resume_id: int):
    is_active = 1 if request.form.get("is_active") == "1" else 0
    execute("UPDATE resumes SET is_active=?, updated_at=? WHERE id=?", (is_active, db_now(), resume_id))
    flash("Статус резюме обновлён.", "success")
    return redirect(url_for("admin"))


if __name__ == "__main__":
    app.run(debug=False)
