"""Shared placement eligibility rules for staff entry and student opportunities."""

from django.db import connection

from .models import RoleSkillRequirement


def eligibility_reasons(student, company_drive, role):
    reasons = []
    if role.company_id != company_drive.company_id:
        return ["This role is not part of the selected company drive."]

    minimum_cgpa_values = [
        value for value in (role.minimum_cgpa, company_drive.minimum_cgpa)
        if value is not None
    ]
    if minimum_cgpa_values and student.cgpa < max(minimum_cgpa_values):
        reasons.append("CGPA is below the drive requirement")

    maximum_backlogs = min(role.maximum_backlogs, company_drive.maximum_backlogs)
    if student.backlogs > maximum_backlogs:
        reasons.append("backlog count is above the drive limit")

    if role.minimum_graduation_year and student.graduation_year < role.minimum_graduation_year:
        reasons.append("graduation year does not meet the role requirement")

    allowed_departments = {
        value.strip().casefold()
        for value in (company_drive.eligible_departments or "").split(",")
        if value.strip()
    }
    if allowed_departments and not {
        student.department.department_code.casefold(),
        student.department.department_name.casefold(),
    }.intersection(allowed_departments):
        reasons.append("department is outside the eligible list")


    skill_requirements = list(RoleSkillRequirement.objects.filter(role_id=role.role_id))
    if skill_requirements:
        ranks = {"beginner": 1, "basic": 1, "novice": 1, "intermediate": 2, "proficient": 2, "advanced": 3, "expert": 4}
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT sk.skill_name, ss.proficiency_level FROM student_skills ss
                   JOIN skills sk ON sk.skill_id = ss.skill_id WHERE ss.student_id = %s""",
                [student.student_id],
            )
            recorded = {name.strip().casefold(): (level or "", ranks.get((level or "").casefold(), 0)) for name, level in cursor.fetchall()}
        for requirement in skill_requirements:
            found = recorded.get(requirement.skill_name.strip().casefold())
            required_rank = ranks.get(requirement.minimum_proficiency.casefold(), 1)
            if found is None:
                reasons.append(f"Required skill {requirement.skill_name} is not recorded in the profile")
            elif found[1] < required_rank:
                reasons.append(f"Recorded {requirement.skill_name} proficiency ({found[0]}) is below {requirement.minimum_proficiency}")

    return reasons
