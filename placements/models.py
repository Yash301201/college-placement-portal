"""Mappings for the existing college_placement_db MySQL schema.

The tables are created by database/college_placement_management_db.sql, so Django must not create or alter them during migrations.
"""

from django.db import models
from django.conf import settings


class Department(models.Model):
    department_id = models.AutoField(primary_key=True)
    department_code = models.CharField(max_length=20, unique=True)
    department_name = models.CharField(max_length=100, unique=True)
    hod_name = models.CharField(max_length=100, null=True, blank=True)
    location = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "departments"
        ordering = ["department_name"]

    def __str__(self):
        return self.department_name


class Student(models.Model):
    student_id = models.AutoField(primary_key=True)
    roll_no = models.CharField(max_length=30, unique=True)
    registration_no = models.CharField(max_length=30, unique=True, null=True, blank=True)
    student_name = models.CharField(max_length=100)
    email = models.EmailField(max_length=100, unique=True)
    phone = models.CharField(max_length=15, unique=True, null=True, blank=True)
    department = models.ForeignKey(
        Department, db_column="department_id", related_name="students", on_delete=models.DO_NOTHING
    )
    admission_year = models.IntegerField()
    graduation_year = models.IntegerField()
    cgpa = models.DecimalField(max_digits=4, decimal_places=2)
    backlogs = models.IntegerField(default=0)
    placement_status = models.CharField(max_length=30, default="Not Placed")

    class Meta:
        managed = False
        db_table = "students"
        ordering = ["roll_no"]

    def __str__(self):
        return f"{self.student_name} ({self.roll_no})"


class StudentPortalAccount(models.Model):
    """Connect a Django login to one existing student row in the supplied schema."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="student_portal_account",
    )
    # The supplied students table is unmanaged. Store its primary key without
    # adding a constraint or changing that existing schema.
    student_id = models.PositiveIntegerField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "student_portal_accounts"
        ordering = ["student_id"]

    def __str__(self):
        return f"Student portal access for student {self.student_id}"


class Skill(models.Model):
    skill_id = models.AutoField(primary_key=True)
    skill_name = models.CharField(max_length=100, unique=True)
    skill_category = models.CharField(max_length=50)
    skill_level = models.CharField(max_length=30, null=True, blank=True)

    class Meta:
        managed = False
        db_table = "skills"
        ordering = ["skill_name"]

    def __str__(self):
        return self.skill_name


class Company(models.Model):
    company_id = models.AutoField(primary_key=True)
    company_name = models.CharField(max_length=150, unique=True)
    industry = models.CharField(max_length=100, null=True, blank=True)
    company_type = models.CharField(max_length=50, null=True, blank=True)
    headquarters = models.CharField(max_length=100, null=True, blank=True)
    website = models.CharField(max_length=200, null=True, blank=True)
    contact_person = models.CharField(max_length=100, null=True, blank=True)
    contact_email = models.CharField(max_length=100, null=True, blank=True)
    contact_phone = models.CharField(max_length=15, null=True, blank=True)
    company_status = models.CharField(max_length=30, default="Active")
    registered_on = models.DateField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "companies"
        ordering = ["company_name"]

    def __str__(self):
        return self.company_name


class JobRole(models.Model):
    role_id = models.AutoField(primary_key=True)
    company = models.ForeignKey(
        Company, db_column="company_id", related_name="job_roles", on_delete=models.DO_NOTHING
    )
    role_title = models.CharField(max_length=100)
    job_description = models.CharField(max_length=500, null=True, blank=True)
    employment_type = models.CharField(max_length=50, default="Full-Time")
    work_location = models.CharField(max_length=100, null=True, blank=True)
    minimum_cgpa = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    maximum_backlogs = models.IntegerField(default=0)
    minimum_graduation_year = models.IntegerField(null=True, blank=True)
    salary_package = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    bond_required = models.BooleanField(default=False)
    role_status = models.CharField(max_length=30, default="Open")

    class Meta:
        managed = False
        db_table = "job_roles"
        ordering = ["role_title"]

    def __str__(self):
        return f"{self.role_title} — {self.company.company_name}"


class PlacementDrive(models.Model):
    drive_id = models.AutoField(primary_key=True)
    drive_name = models.CharField(max_length=150)
    academic_year = models.CharField(max_length=20)
    drive_type = models.CharField(max_length=50, default="On-Campus")
    registration_start = models.DateField(null=True, blank=True)
    registration_end = models.DateField(null=True, blank=True)
    drive_start_date = models.DateField(null=True, blank=True)
    drive_end_date = models.DateField(null=True, blank=True)
    venue = models.CharField(max_length=150, null=True, blank=True)
    drive_status = models.CharField(max_length=30, default="Upcoming")

    class Meta:
        managed = False
        db_table = "placement_drives"
        ordering = ["-drive_start_date", "drive_name"]

    def __str__(self):
        return self.drive_name


class CompanyDrive(models.Model):
    company_drive_id = models.AutoField(primary_key=True)
    drive = models.ForeignKey(
        PlacementDrive, db_column="drive_id", related_name="company_drives", on_delete=models.DO_NOTHING
    )
    company = models.ForeignKey(
        Company, db_column="company_id", related_name="company_drives", on_delete=models.DO_NOTHING
    )
    registration_start = models.DateField(null=True, blank=True)
    registration_end = models.DateField(null=True, blank=True)
    eligible_departments = models.CharField(max_length=500, null=True, blank=True)
    minimum_cgpa = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    maximum_backlogs = models.IntegerField(default=0)
    drive_status = models.CharField(max_length=30, default="Open")

    class Meta:
        managed = False
        db_table = "company_drives"
        unique_together = [("drive", "company")]

    def __str__(self):
        return f"{self.company} — {self.drive}"


class Application(models.Model):
    application_id = models.AutoField(primary_key=True)
    student = models.ForeignKey(
        Student, db_column="student_id", related_name="applications", on_delete=models.DO_NOTHING
    )
    company_drive = models.ForeignKey(
        CompanyDrive, db_column="company_drive_id", related_name="applications", on_delete=models.DO_NOTHING
    )
    role = models.ForeignKey(
        JobRole, db_column="role_id", related_name="applications", on_delete=models.DO_NOTHING
    )
    application_date = models.DateField()
    application_status = models.CharField(max_length=30, default="Applied")
    eligibility_status = models.CharField(max_length=30, default="Pending")
    resume_submitted = models.BooleanField(default=False)
    remarks = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        managed = False
        db_table = "applications"
        unique_together = [("student", "company_drive", "role")]
        ordering = ["-application_date"]

    def __str__(self):
        return f"{self.student} — {self.role}"


class InterviewRound(models.Model):
    round_id = models.AutoField(primary_key=True)
    application = models.ForeignKey(
        Application, db_column="application_id", related_name="interview_rounds", on_delete=models.DO_NOTHING
    )
    round_number = models.IntegerField()
    round_name = models.CharField(max_length=100)
    scheduled_date = models.DateTimeField(null=True, blank=True)
    interview_mode = models.CharField(max_length=30, null=True, blank=True)
    interviewer_name = models.CharField(max_length=100, null=True, blank=True)
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    round_status = models.CharField(max_length=30, default="Scheduled")
    feedback = models.CharField(max_length=500, null=True, blank=True)

    class Meta:
        managed = False
        db_table = "interview_rounds"
        unique_together = [("application", "round_number")]

    def __str__(self):
        return f"{self.round_name} — {self.application}"


class Selection(models.Model):
    selection_id = models.AutoField(primary_key=True)
    application = models.OneToOneField(
        Application, db_column="application_id", related_name="selection", on_delete=models.DO_NOTHING
    )
    selection_date = models.DateField()
    selection_status = models.CharField(max_length=30)
    final_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    selected_by = models.CharField(max_length=100, null=True, blank=True)
    remarks = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        managed = False
        db_table = "selections"

    def __str__(self):
        return f"{self.application} — {self.selection_status}"


class Offer(models.Model):
    offer_id = models.AutoField(primary_key=True)
    selection = models.OneToOneField(
        Selection, db_column="selection_id", related_name="offer", on_delete=models.DO_NOTHING
    )
    offer_date = models.DateField()
    joining_date = models.DateField(null=True, blank=True)
    annual_ctc = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    offer_type = models.CharField(max_length=50, default="Full-Time")
    offer_status = models.CharField(max_length=30, default="Issued")
    offer_reference_no = models.CharField(max_length=50, unique=True, null=True, blank=True)

    class Meta:
        managed = False
        db_table = "offers"

    def __str__(self):
        return f"Offer {self.offer_reference_no or self.offer_id}"

class SemesterPerformance(models.Model):
    """Term-level academic snapshot linked to an existing unmanaged student row."""
    student_id = models.PositiveIntegerField(db_index=True)
    academic_year = models.CharField(max_length=9)
    semester = models.PositiveSmallIntegerField()
    sgpa = models.DecimalField(max_digits=4, decimal_places=2)
    cumulative_cgpa = models.DecimalField(max_digits=4, decimal_places=2)
    backlogs = models.PositiveSmallIntegerField(default=0)
    recorded_on = models.DateField(auto_now_add=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["academic_year", "semester"]
        constraints = [models.UniqueConstraint(fields=["student_id", "academic_year", "semester"], name="uniq_student_semester_record")]

    def __str__(self):
        return f"Student {self.student_id} · {self.academic_year} semester {self.semester}"


class RoleSkillRequirement(models.Model):
    PROFICIENCY = [("Beginner", "Beginner"), ("Intermediate", "Intermediate"), ("Advanced", "Advanced"), ("Expert", "Expert")]
    role = models.ForeignKey(JobRole, db_column="role_id", related_name="skill_requirements", on_delete=models.DO_NOTHING, db_constraint=False)
    skill_name = models.CharField(max_length=100)
    minimum_proficiency = models.CharField(max_length=20, choices=PROFICIENCY, default="Beginner")

    class Meta:
        ordering = ["role_id", "skill_name"]
        constraints = [models.UniqueConstraint(fields=["role", "skill_name"], name="uniq_role_skill_requirement")]

    def __str__(self):
        return f"Role {self.role_id} requires {self.skill_name} ({self.minimum_proficiency})"


class InterviewCategoryScore(models.Model):
    CATEGORIES = [("Technical skills", "Technical skills"), ("Communication", "Communication"), ("Problem solving", "Problem solving"), ("Role knowledge", "Role knowledge"), ("Teamwork", "Teamwork")]
    interview_round_id = models.PositiveIntegerField(db_index=True)
    category = models.CharField(max_length=40, choices=CATEGORIES)
    score = models.DecimalField(max_digits=5, decimal_places=2)
    feedback = models.CharField(max_length=500, blank=True)
    visible_to_student = models.BooleanField(default=False)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="interview_category_scores")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category"]
        constraints = [models.UniqueConstraint(fields=["interview_round_id", "category"], name="uniq_round_interview_category")]

    def __str__(self):
        return f"Round {self.interview_round_id} · {self.category}: {self.score}"


class PortalReminder(models.Model):
    TYPES = [("Deadline", "Application deadline"), ("Interview", "Interview"), ("Offer", "Offer response"), ("Follow-up", "Follow-up")]
    student_id = models.PositiveIntegerField(db_index=True)
    reminder_type = models.CharField(max_length=20, choices=TYPES, default="Follow-up")
    title = models.CharField(max_length=120)
    message = models.CharField(max_length=500, blank=True)
    due_at = models.DateTimeField(db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="placement_reminders")
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["due_at", "id"]

    def __str__(self):
        return f"{self.title} · student {self.student_id}"


class OfferResponseDeadline(models.Model):
    offer_id = models.PositiveIntegerField(unique=True)
    response_deadline = models.DateTimeField(db_index=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="offer_deadlines")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["response_deadline"]

    def __str__(self):
        return f"Offer {self.offer_id} response by {self.response_deadline}"


class PlacementStatusHistory(models.Model):
    RECORD_TYPES = [("Application", "Application"), ("Selection", "Selection"), ("Offer", "Offer")]
    student_id = models.PositiveIntegerField(db_index=True)
    record_type = models.CharField(max_length=20, choices=RECORD_TYPES)
    record_id = models.PositiveIntegerField(db_index=True)
    field_name = models.CharField(max_length=40, default="status")
    old_value = models.CharField(max_length=80, blank=True)
    new_value = models.CharField(max_length=80)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="placement_status_changes")
    changed_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-changed_at", "-id"]

    def __str__(self):
        return f"{self.record_type} {self.record_id}: {self.old_value} → {self.new_value}"


class StudentDocument(models.Model):
    """Private uploads served only through an authenticated, student-scoped view."""
    student_id = models.PositiveIntegerField(db_index=True)
    document = models.FileField(upload_to="private/student-documents/")
    original_name = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"Private document for student {self.student_id}: {self.original_name}"
