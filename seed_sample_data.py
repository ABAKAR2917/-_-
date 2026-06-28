from datetime import UTC, datetime

import pymysql
from werkzeug.security import generate_password_hash


DB = {
    "host": "127.0.0.1",
    "user": "root",
    "password": "",
    "database": "employment_platform",
    "charset": "utf8mb4",
}

NOW = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

APPLICANTS = [
    ("Алексей Смирнов", "alexey.smirnov@mail.ru", "Москва", "Высшее", "Программная инженерия", 3.0, "Python-разработчик", 130000, "Python, Flask, SQL, Docker", 0.82),
    ("Мария Иванова", "maria.ivanova@mail.ru", "Санкт-Петербург", "Бакалавриат", "Маркетинг", 2.0, "Маркетолог", 85000, "SMM, аналитика, копирайтинг, CRM", 0.74),
    ("Дмитрий Кузнецов", "d.kuznetsov@mail.ru", "Екатеринбург", "Среднее специальное", "Системное администрирование", 4.0, "Системный администратор", 95000, "Linux, Windows Server, Docker, Git", 0.78),
    ("Анна Петрова", "anna.petrova@mail.ru", "Казань", "Высшее", "Бухгалтерский учет", 5.0, "Бухгалтер", 75000, "1C, Excel, отчетность, налоги", 0.86),
    ("Игорь Волков", "igor.volkov@mail.ru", "Новосибирск", "Магистратура", "Анализ данных", 2.5, "Аналитик данных", 120000, "Python, SQL, Power BI, статистика", 0.8),
    ("Елена Соколова", "elena.sokolova@mail.ru", "Оренбург", "Высшее", "Управление персоналом", 3.0, "HR-менеджер", 70000, "подбор персонала, интервью, адаптация, HRM", 0.77),
    ("Никита Морозов", "nikita.morozov@mail.ru", "Пермь", "Бакалавриат", "Веб-разработка", 1.5, "Frontend-разработчик", 90000, "HTML, CSS, JavaScript, React", 0.72),
    ("Ольга Орлова", "olga.orlova@mail.ru", "Уфа", "Высшее", "Менеджмент", 4.5, "Менеджер по продажам", 100000, "продажи, переговоры, CRM, презентации", 0.84),
    ("Сергей Федоров", "sergey.fedorov@mail.ru", "Челябинск", "Среднее специальное", "Техническая поддержка", 2.0, "Специалист технической поддержки", 60000, "коммуникация, Windows, helpdesk, support", 0.68),
    ("Кристина Павлова", "k.pavlova@mail.ru", "Тюмень", "Высшее", "Юриспруденция", 3.5, "Юрист", 90000, "договоры, претензии, правовой анализ", 0.79),
    ("Роман Егоров", "roman.egorov@mail.ru", "Москва", "Высшее", "Backend-разработка", 5.0, "Backend-разработчик", 180000, "Python, Django, PostgreSQL, Redis", 0.9),
    ("Виктория Белова", "v.belova@mail.ru", "Самара", "Бакалавриат", "Дизайн интерфейсов", 2.0, "UI/UX дизайнер", 95000, "Figma, UX, прототипирование, дизайн-системы", 0.76),
    ("Артем Захаров", "artem.zakharov@mail.ru", "Екатеринбург", "Высшее", "Информационная безопасность", 3.0, "Специалист ИБ", 140000, "Linux, сети, SIEM, безопасность", 0.81),
    ("Дарья Михайлова", "daria.mikhailova@mail.ru", "Казань", "Магистратура", "Проектное управление", 6.0, "Project Manager", 150000, "Agile, Scrum, Jira, коммуникация", 0.88),
    ("Павел Новиков", "pavel.novikov@mail.ru", "Нижний Новгород", "Среднее", "Логистика", 4.0, "Логист", 80000, "логистика, Excel, склад, маршрутизация", 0.7),
]

VACANCIES = [
    ("Python-разработчик", "Москва", "Гибрид", "Высшее", 2.0, "Разработка сервисов на Flask и интеграция с MySQL.", "Гибридный график, ДМС, премии.", 150000, "Полная занятость", "Python, Flask, SQL, Docker"),
    ("Маркетолог", "Санкт-Петербург", "Офис", "Бакалавриат", 1.0, "Ведение рекламных кампаний и аналитика.", "Офис, обучение, бонусы.", 90000, "Полная занятость", "SMM, аналитика, CRM, копирайтинг"),
    ("Системный администратор", "Екатеринбург", "Офис", "Среднее специальное", 3.0, "Поддержка серверов и рабочих станций.", "Официальное оформление.", 100000, "Полная занятость", "Linux, Windows Server, Docker"),
    ("Бухгалтер", "Казань", "Офис", "Высшее", 3.0, "Ведение учета и подготовка отчетности.", "Стабильная компания.", 80000, "Полная занятость", "1C, Excel, отчетность, налоги"),
    ("Аналитик данных", "Новосибирск", "Удаленно", "Высшее", 2.0, "Подготовка отчетов и построение BI-дашбордов.", "Удаленная работа.", 130000, "Удаленная работа", "Python, SQL, Power BI, статистика"),
    ("HR-менеджер", "Оренбург", "Офис", "Высшее", 2.0, "Поиск, интервью и адаптация персонала.", "Комфортный офис.", 75000, "Полная занятость", "подбор персонала, интервью, HRM"),
    ("Frontend-разработчик", "Пермь", "Гибрид", "Бакалавриат", 1.0, "Разработка интерфейсов на React.", "Гибрид, молодой коллектив.", 110000, "Полная занятость", "HTML, CSS, JavaScript, React"),
    ("Менеджер по продажам", "Уфа", "Офис", "Среднее специальное", 2.0, "Продажа B2B услуг и ведение CRM.", "Оклад плюс процент.", 120000, "Полная занятость", "продажи, переговоры, CRM"),
    ("Специалист технической поддержки", "Челябинск", "Удаленно", "Среднее", 0.5, "Помощь пользователям и обработка заявок.", "Удаленно, сменный график.", 65000, "Удаленная работа", "коммуникация, Windows, helpdesk, support"),
    ("Юрист", "Тюмень", "Офис", "Высшее", 3.0, "Договорная работа и претензионная деятельность.", "Офис, карьерный рост.", 95000, "Полная занятость", "договоры, претензии, правовой анализ"),
    ("Backend-разработчик", "Москва", "Удаленно", "Высшее", 4.0, "Разработка API и высоконагруженных сервисов.", "Удаленка, сильная команда.", 200000, "Удаленная работа", "Python, Django, PostgreSQL, Redis"),
    ("UI/UX дизайнер", "Самара", "Гибрид", "Бакалавриат", 1.5, "Проектирование интерфейсов и дизайн-систем.", "Гибридный формат.", 100000, "Проектная работа", "Figma, UX, прототипирование, дизайн-системы"),
    ("Специалист ИБ", "Екатеринбург", "Офис", "Высшее", 2.0, "Мониторинг безопасности и анализ инцидентов.", "Официальное оформление.", 150000, "Полная занятость", "Linux, сети, SIEM, безопасность"),
    ("Project Manager", "Казань", "Гибрид", "Высшее", 4.0, "Управление IT-проектами и коммуникацией.", "Гибкий график.", 160000, "Полная занятость", "Agile, Scrum, Jira, коммуникация"),
    ("Логист", "Нижний Новгород", "Офис", "Среднее", 2.0, "Планирование маршрутов и работа со складом.", "Стабильная компания.", 85000, "Полная занятость", "логистика, Excel, склад, маршрутизация"),
]


def main() -> None:
    con = pymysql.connect(**DB)
    cur = con.cursor()
    cur.execute("SET FOREIGN_KEY_CHECKS=0")
    for table in ["notifications", "model_runs", "applications", "vacancies", "resumes", "companies"]:
        cur.execute(f"TRUNCATE TABLE {table}")
    cur.execute("DELETE FROM users WHERE role <> 'admin'")
    cur.execute("SET FOREIGN_KEY_CHECKS=1")

    employer_hash = generate_password_hash("employer123")
    user_hash = generate_password_hash("user123")

    cur.execute(
        "INSERT INTO users(full_name,email,password_hash,role,created_at) VALUES(%s,%s,%s,'employer',%s)",
        ("HR ПрофКарьера", "hr.profcareer@mail.ru", employer_hash, NOW),
    )
    employer_id = cur.lastrowid
    cur.execute(
        "INSERT INTO companies(owner_id,name,inn,industry,city,contacts,is_verified,created_at) VALUES(%s,%s,%s,%s,%s,%s,1,%s)",
        (employer_id, "ПрофКарьера", "7700000000", "Подбор персонала и IT", "Москва", "hr@profcareer.ru", NOW),
    )
    company_id = cur.lastrowid

    applicant_ids = []
    for index, row in enumerate(APPLICANTS, start=1):
        name, email, city, edu, spec, exp, pos, salary, skills, level = row
        cur.execute(
            "INSERT INTO users(full_name,email,password_hash,role,created_at) VALUES(%s,%s,%s,'applicant',%s)",
            (name, email, user_hash, NOW),
        )
        user_id = cur.lastrowid
        applicant_ids.append(user_id)
        birth_date = datetime(1995 + (index % 8), (index % 12) + 1, min((index * 2) % 28 + 1, 28)).strftime("%Y-%m-%d")
        gender = "Женский" if index in (2, 4, 6, 10, 12, 14) else "Мужской"
        phone = f"+7 900 100 {index:02d} {index:02d}"
        cur.execute(
            """
            INSERT INTO resumes(user_id, gender, birth_date, city, phone, education_level, specialty,
            experience_years, desired_position, desired_salary, skills, skills_level, is_active, updated_at)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1,%s)
            """,
            (user_id, gender, birth_date, city, phone, edu, spec, exp, pos, salary, skills, level, NOW),
        )

    vacancy_ids = []
    for row in VACANCIES:
        title, city, workplace, edu, exp, duties, conditions, salary, emp_type, skills = row
        cur.execute(
            """
            INSERT INTO vacancies(company_id,title,city,workplace,education_required,experience_required,duties,conditions,
            salary,employment_type,required_skills,is_active,needs_attention,created_at,last_confirmed_at)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1,0,%s,%s)
            """,
            (company_id, title, city, workplace, edu, exp, duties, conditions, salary, emp_type, skills, NOW, NOW),
        )
        vacancy_ids.append(cur.lastrowid)

    for index, user_id in enumerate(applicant_ids):
        cur.execute(
            "INSERT INTO applications(vacancy_id,applicant_id,status,reason,score,created_at,updated_at) VALUES(%s,%s,'invited','Подходит по ключевым требованиям',0.85,%s,%s)",
            (vacancy_ids[index], user_id, NOW, NOW),
        )
        cur.execute(
            "INSERT INTO applications(vacancy_id,applicant_id,status,reason,score,created_at,updated_at) VALUES(%s,%s,'rejected','Недостаточное совпадение профиля',0.35,%s,%s)",
            (vacancy_ids[(index + 5) % len(vacancy_ids)], user_id, NOW, NOW),
        )

    con.commit()
    for table in ["users", "companies", "resumes", "vacancies", "applications"]:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        print(table, cur.fetchone()[0])
    con.close()


if __name__ == "__main__":
    main()
