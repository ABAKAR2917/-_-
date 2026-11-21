CREATE DATABASE IF NOT EXISTS employment_platform
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE employment_platform;

CREATE TABLE users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  full_name VARCHAR(150) NOT NULL,
  email VARCHAR(180) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  role ENUM('applicant', 'employer', 'admin') NOT NULL,
  email_login_code_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  created_at DATETIME NOT NULL
);

CREATE TABLE companies (
  id INT AUTO_INCREMENT PRIMARY KEY,
  owner_id INT NOT NULL,
  name VARCHAR(180) NOT NULL,
  inn VARCHAR(20) NOT NULL,
  industry VARCHAR(160) NOT NULL,
  city VARCHAR(120) NOT NULL,
  contacts VARCHAR(255) NOT NULL,
  description TEXT,
  company_size VARCHAR(80),
  logo VARCHAR(255),
  is_verified BOOLEAN NOT NULL DEFAULT FALSE,
  created_at DATETIME NOT NULL,
  CONSTRAINT fk_companies_owner
    FOREIGN KEY (owner_id) REFERENCES users(id)
    ON DELETE CASCADE
);

CREATE TABLE resumes (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL UNIQUE,
  gender VARCHAR(40),
  birth_date DATE,
  city VARCHAR(120) NOT NULL,
  phone VARCHAR(80) NOT NULL,
  education_level VARCHAR(120) NOT NULL,
  specialty VARCHAR(180) NOT NULL,
  experience_years DECIMAL(5,2) NOT NULL DEFAULT 0,
  desired_position VARCHAR(180) NOT NULL,
  desired_salary DECIMAL(12,2) NOT NULL DEFAULT 0,
  skills TEXT NOT NULL,
  skills_level DECIMAL(4,3) NOT NULL DEFAULT 0,
  work_experience TEXT,
  education_history TEXT,
  languages TEXT,
  certificates TEXT,
  portfolio_links TEXT,
  availability_status VARCHAR(120),
  resume_file VARCHAR(255),
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  updated_at DATETIME NOT NULL,
  CONSTRAINT fk_resumes_user
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON DELETE CASCADE,
  INDEX idx_resumes_city (city),
  INDEX idx_resumes_active_updated (is_active, updated_at)
);

CREATE TABLE vacancies (
  id INT AUTO_INCREMENT PRIMARY KEY,
  company_id INT NOT NULL,
  title VARCHAR(180) NOT NULL,
  city VARCHAR(120) NOT NULL,
  workplace VARCHAR(160) NOT NULL,
  education_required VARCHAR(120) NOT NULL,
  experience_required DECIMAL(5,2) NOT NULL DEFAULT 0,
  duties TEXT NOT NULL,
  conditions TEXT NOT NULL,
  salary DECIMAL(12,2) NOT NULL DEFAULT 0,
  employment_type VARCHAR(120) NOT NULL,
  required_skills TEXT NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  needs_attention BOOLEAN NOT NULL DEFAULT FALSE,
  created_at DATETIME NOT NULL,
  last_confirmed_at DATETIME NOT NULL,
  CONSTRAINT fk_vacancies_company
    FOREIGN KEY (company_id) REFERENCES companies(id)
    ON DELETE CASCADE,
  INDEX idx_vacancies_search (is_active, city, salary, employment_type),
  INDEX idx_vacancies_attention (needs_attention, is_active)
);

CREATE TABLE applications (
  id INT AUTO_INCREMENT PRIMARY KEY,
  vacancy_id INT NOT NULL,
  applicant_id INT NOT NULL,
  status ENUM('sent', 'viewed', 'invited', 'rejected') NOT NULL DEFAULT 'sent',
  reason VARCHAR(255),
  score DECIMAL(10,4),
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  CONSTRAINT fk_applications_vacancy
    FOREIGN KEY (vacancy_id) REFERENCES vacancies(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_applications_applicant
    FOREIGN KEY (applicant_id) REFERENCES users(id)
    ON DELETE CASCADE,
  CONSTRAINT uq_application_once UNIQUE (vacancy_id, applicant_id),
  INDEX idx_applications_status (status),
  INDEX idx_applications_applicant (applicant_id, updated_at)
);

CREATE TABLE model_runs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  applicant_id INT NOT NULL,
  weights TEXT NOT NULL,
  threshold DECIMAL(10,4) NOT NULL,
  created_at DATETIME NOT NULL,
  CONSTRAINT fk_model_runs_applicant
    FOREIGN KEY (applicant_id) REFERENCES users(id)
    ON DELETE CASCADE,
  INDEX idx_model_runs_applicant (applicant_id, created_at)
);

CREATE TABLE notifications (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  title VARCHAR(180) NOT NULL,
  body TEXT NOT NULL,
  is_read BOOLEAN NOT NULL DEFAULT FALSE,
  created_at DATETIME NOT NULL,
  CONSTRAINT fk_notifications_user
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON DELETE CASCADE,
  INDEX idx_notifications_user (user_id, is_read, created_at)
);

CREATE TABLE favorites (
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
);

CREATE TABLE application_history (
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
);

CREATE TABLE vacancy_views (
  id INT AUTO_INCREMENT PRIMARY KEY,
  vacancy_id INT NOT NULL,
  viewer_id INT,
  created_at DATETIME NOT NULL,
  CONSTRAINT fk_vacancy_views_vacancy
    FOREIGN KEY (vacancy_id) REFERENCES vacancies(id)
    ON DELETE CASCADE,
  INDEX idx_vacancy_views (vacancy_id, created_at)
);

CREATE TABLE employer_notes (
  id INT AUTO_INCREMENT PRIMARY KEY,
  employer_id INT NOT NULL,
  resume_id INT NOT NULL,
  note TEXT NOT NULL,
  created_at DATETIME NOT NULL,
  INDEX idx_employer_notes (employer_id, resume_id, created_at)
);

CREATE TABLE reports (
  id INT AUTO_INCREMENT PRIMARY KEY,
  reporter_id INT,
  item_type ENUM('vacancy') NOT NULL,
  item_id INT NOT NULL,
  reason VARCHAR(255) NOT NULL,
  created_at DATETIME NOT NULL,
  INDEX idx_reports (item_type, item_id, created_at)
);

CREATE TABLE messages (
  id INT AUTO_INCREMENT PRIMARY KEY,
  vacancy_id INT NOT NULL,
  sender_id INT NOT NULL,
  receiver_id INT NOT NULL,
  body TEXT NOT NULL,
  is_read BOOLEAN NOT NULL DEFAULT FALSE,
  created_at DATETIME NOT NULL,
  INDEX idx_messages_receiver (receiver_id, is_read, created_at),
  INDEX idx_messages_vacancy (vacancy_id, created_at)
);

CREATE TABLE login_codes (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  code_hash VARCHAR(255) NOT NULL,
  expires_at DATETIME NOT NULL,
  used_at DATETIME,
  created_at DATETIME NOT NULL,
  INDEX idx_login_codes_user (user_id, expires_at, used_at)
);
