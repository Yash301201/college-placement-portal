-- =====================================================================
-- PART 7: SQL QUERIES
-- College Placement Management and Recruitment Database
-- MySQL 8.0+
-- These manual report queries match the portal's Django ORM reports.
-- The portal database is named college_placement_db.
-- =====================================================================

USE college_placement_db;

-- Q1. Display students with their department names
SELECT s.student_id, s.roll_no, s.student_name, d.department_name, s.cgpa, s.placement_status
FROM students AS s
INNER JOIN departments AS d ON s.department_id = d.department_id;

-- Q2. Find students with CGPA of 8 or above and no backlogs
SELECT student_name, cgpa, backlogs
FROM students
WHERE cgpa >= 8.00 AND backlogs = 0
ORDER BY cgpa DESC;

-- Q3. Count students in each department
SELECT d.department_name, COUNT(s.student_id) AS total_students
FROM departments AS d
LEFT JOIN students AS s ON d.department_id = s.department_id
GROUP BY d.department_id, d.department_name
ORDER BY total_students DESC;

-- Q4. Find departments with an average CGPA above 8
SELECT d.department_name, ROUND(AVG(s.cgpa), 2) AS average_cgpa
FROM departments AS d
INNER JOIN students AS s ON d.department_id = s.department_id
GROUP BY d.department_id, d.department_name
HAVING AVG(s.cgpa) > 8.00;

-- Q5. Display companies and their job roles with salary packages
SELECT c.company_name, j.role_title, j.work_location, j.salary_package
FROM companies AS c
INNER JOIN job_roles AS j ON c.company_id = j.company_id
ORDER BY j.salary_package DESC;

-- Q6. Find job roles whose salary is above the average salary package
SELECT role_title, salary_package
FROM job_roles
WHERE salary_package > (SELECT AVG(salary_package) FROM job_roles)
ORDER BY salary_package DESC;

-- Q7. Display application details with student and company names
SELECT a.application_id, s.student_name, c.company_name, j.role_title,
       a.application_date, a.application_status, a.eligibility_status
FROM applications AS a
INNER JOIN students AS s ON a.student_id = s.student_id
INNER JOIN company_drives AS cd ON a.company_drive_id = cd.company_drive_id
INNER JOIN companies AS c ON cd.company_id = c.company_id
INNER JOIN job_roles AS j ON a.role_id = j.role_id
ORDER BY a.application_date DESC;

-- Q8. Count applications by application status
SELECT application_status, COUNT(*) AS total_applications
FROM applications
GROUP BY application_status
ORDER BY total_applications DESC;

-- Q9. Display selected students and their offer details
SELECT s.student_name, c.company_name, j.role_title, sel.selection_status,
       o.annual_ctc, o.offer_status
FROM selections AS sel
INNER JOIN applications AS a ON sel.application_id = a.application_id
INNER JOIN students AS s ON a.student_id = s.student_id
INNER JOIN company_drives AS cd ON a.company_drive_id = cd.company_drive_id
INNER JOIN companies AS c ON cd.company_id = c.company_id
INNER JOIN job_roles AS j ON a.role_id = j.role_id
LEFT JOIN offers AS o ON sel.selection_id = o.selection_id
ORDER BY o.annual_ctc DESC;

-- Q10. Show department-wise placement summary
SELECT d.department_name,
       COUNT(s.student_id) AS total_students,
       SUM(CASE WHEN s.placement_status = 'Placed' THEN 1 ELSE 0 END) AS placed_students,
       SUM(CASE WHEN s.placement_status = 'Not Placed' THEN 1 ELSE 0 END) AS not_placed_students,
       ROUND(AVG(s.cgpa), 2) AS average_cgpa
FROM departments AS d
LEFT JOIN students AS s ON d.department_id = s.department_id
GROUP BY d.department_id, d.department_name
ORDER BY placed_students DESC;
