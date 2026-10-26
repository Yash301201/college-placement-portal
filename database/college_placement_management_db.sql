-- College Placement Management database schema for the portal.
-- The MySQL database name is college_placement_db, matching config/settings.py.
-- This is the project schema. It creates empty tables and contains no sample rows.
CREATE DATABASE IF NOT EXISTS college_placement_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE college_placement_db;

CREATE TABLE IF NOT EXISTS departments (
    department_id INT AUTO_INCREMENT PRIMARY KEY,
    department_code VARCHAR(20) NOT NULL UNIQUE,
    department_name VARCHAR(100) NOT NULL UNIQUE,
    hod_name VARCHAR(100),
    location VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS students (
    student_id INT AUTO_INCREMENT PRIMARY KEY,
    roll_no VARCHAR(30) NOT NULL UNIQUE,
    registration_no VARCHAR(30) UNIQUE,
    student_name VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    phone VARCHAR(15) UNIQUE,
    department_id INT NOT NULL,
    admission_year YEAR NOT NULL,
    graduation_year YEAR NOT NULL,
    cgpa DECIMAL(4,2) NOT NULL,
    backlogs INT DEFAULT 0,
    placement_status VARCHAR(30) DEFAULT 'Not Placed',

    CONSTRAINT chk_student_cgpa
        CHECK (cgpa BETWEEN 0.00 AND 10.00),

    CONSTRAINT chk_student_backlogs
        CHECK (backlogs >= 0),

    FOREIGN KEY (department_id)
        REFERENCES departments(department_id)
);

CREATE TABLE IF NOT EXISTS skills (
    skill_id INT AUTO_INCREMENT PRIMARY KEY,
    skill_name VARCHAR(100) NOT NULL UNIQUE,
    skill_category VARCHAR(50) NOT NULL,
    skill_level VARCHAR(30)
);

CREATE TABLE IF NOT EXISTS student_skills (
    student_id INT NOT NULL,
    skill_id INT NOT NULL,
    proficiency_level VARCHAR(30) NOT NULL,
    years_of_experience DECIMAL(3,1) DEFAULT 0.0,

    PRIMARY KEY (student_id, skill_id),

    FOREIGN KEY (student_id)
        REFERENCES students(student_id),

    FOREIGN KEY (skill_id)
        REFERENCES skills(skill_id),

    CONSTRAINT chk_skill_experience
        CHECK (years_of_experience >= 0)
);

CREATE TABLE IF NOT EXISTS companies (
    company_id INT AUTO_INCREMENT PRIMARY KEY,
    company_name VARCHAR(150) NOT NULL UNIQUE,
    industry VARCHAR(100),
    company_type VARCHAR(50),
    headquarters VARCHAR(100),
    website VARCHAR(200),
    contact_person VARCHAR(100),
    contact_email VARCHAR(100),
    contact_phone VARCHAR(15),
    company_status VARCHAR(30) DEFAULT 'Active',
    registered_on DATE
);

CREATE TABLE IF NOT EXISTS job_roles (
    role_id INT AUTO_INCREMENT PRIMARY KEY,
    company_id INT NOT NULL,
    role_title VARCHAR(100) NOT NULL,
    job_description VARCHAR(500),
    employment_type VARCHAR(50) DEFAULT 'Full-Time',
    work_location VARCHAR(100),
    minimum_cgpa DECIMAL(4,2),
    maximum_backlogs INT DEFAULT 0,
    minimum_graduation_year YEAR,
    salary_package DECIMAL(10,2),
    bond_required BOOLEAN DEFAULT FALSE,
    role_status VARCHAR(30) DEFAULT 'Open',

    CONSTRAINT chk_role_cgpa
        CHECK (minimum_cgpa BETWEEN 0.00 AND 10.00),

    CONSTRAINT chk_role_backlogs
        CHECK (maximum_backlogs >= 0),

    FOREIGN KEY (company_id)
        REFERENCES companies(company_id)
);

CREATE TABLE IF NOT EXISTS placement_drives (
    drive_id INT AUTO_INCREMENT PRIMARY KEY,
    drive_name VARCHAR(150) NOT NULL,
    academic_year VARCHAR(20) NOT NULL,
    drive_type VARCHAR(50) DEFAULT 'On-Campus',
    registration_start DATE,
    registration_end DATE,
    drive_start_date DATE,
    drive_end_date DATE,
    venue VARCHAR(150),
    drive_status VARCHAR(30) DEFAULT 'Upcoming',

    CONSTRAINT chk_drive_dates
        CHECK (registration_end >= registration_start)
);

CREATE TABLE IF NOT EXISTS company_drives (
    company_drive_id INT AUTO_INCREMENT PRIMARY KEY,
    drive_id INT NOT NULL,
    company_id INT NOT NULL,
    registration_start DATE,
    registration_end DATE,
    eligible_departments VARCHAR(500),
    minimum_cgpa DECIMAL(4,2),
    maximum_backlogs INT DEFAULT 0,
    drive_status VARCHAR(30) DEFAULT 'Open',

    UNIQUE (drive_id, company_id),

    CONSTRAINT chk_company_drive_cgpa
        CHECK (minimum_cgpa BETWEEN 0.00 AND 10.00),

    CONSTRAINT chk_company_drive_backlogs
        CHECK (maximum_backlogs >= 0),

    FOREIGN KEY (drive_id)
        REFERENCES placement_drives(drive_id),

    FOREIGN KEY (company_id)
        REFERENCES companies(company_id)
);

CREATE TABLE IF NOT EXISTS applications (
    application_id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    company_drive_id INT NOT NULL,
    role_id INT NOT NULL,
    application_date DATE NOT NULL,
    application_status VARCHAR(30) DEFAULT 'Applied',
    eligibility_status VARCHAR(30) DEFAULT 'Pending',
    resume_submitted BOOLEAN DEFAULT FALSE,
    remarks VARCHAR(255),

    UNIQUE (student_id, company_drive_id, role_id),

    FOREIGN KEY (student_id)
        REFERENCES students(student_id),

    FOREIGN KEY (company_drive_id)
        REFERENCES company_drives(company_drive_id),

    FOREIGN KEY (role_id)
        REFERENCES job_roles(role_id)
);

CREATE TABLE IF NOT EXISTS interview_rounds (
    round_id INT AUTO_INCREMENT PRIMARY KEY,
    application_id INT NOT NULL,
    round_number INT NOT NULL,
    round_name VARCHAR(100) NOT NULL,
    scheduled_date DATETIME,
    interview_mode VARCHAR(30),
    interviewer_name VARCHAR(100),
    score DECIMAL(5,2),
    round_status VARCHAR(30) DEFAULT 'Scheduled',
    feedback VARCHAR(500),

    UNIQUE (application_id, round_number),

    CONSTRAINT chk_round_number
        CHECK (round_number > 0),

    CONSTRAINT chk_round_score
        CHECK (score IS NULL OR score BETWEEN 0 AND 100),

    FOREIGN KEY (application_id)
        REFERENCES applications(application_id)
);

CREATE TABLE IF NOT EXISTS selections (
    selection_id INT AUTO_INCREMENT PRIMARY KEY,
    application_id INT NOT NULL UNIQUE,
    selection_date DATE NOT NULL,
    selection_status VARCHAR(30) NOT NULL,
    final_score DECIMAL(5,2),
    selected_by VARCHAR(100),
    remarks VARCHAR(255),

    CONSTRAINT chk_selection_score
        CHECK (final_score IS NULL OR final_score BETWEEN 0 AND 100),

    FOREIGN KEY (application_id)
        REFERENCES applications(application_id)
);

CREATE TABLE IF NOT EXISTS offers (
    offer_id INT AUTO_INCREMENT PRIMARY KEY,
    selection_id INT NOT NULL UNIQUE,
    offer_date DATE NOT NULL,
    joining_date DATE,
    annual_ctc DECIMAL(10,2),
    offer_type VARCHAR(50) DEFAULT 'Full-Time',
    offer_status VARCHAR(30) DEFAULT 'Issued',
    offer_reference_no VARCHAR(50) UNIQUE,

    CONSTRAINT chk_offer_ctc
        CHECK (annual_ctc >= 0),

    CONSTRAINT chk_joining_date
        CHECK (joining_date IS NULL OR joining_date >= offer_date),

    FOREIGN KEY (selection_id)
        REFERENCES selections(selection_id)
);
