from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.forms import PasswordResetForm

from .models import (
    Application,
    Company,
    CompanyDrive,
    InterviewRound,
    JobRole,
    Offer,
    PlacementDrive,
    Selection,
    Student,
    SemesterPerformance, InterviewCategoryScore, PortalReminder, StudentDocument, StudentPortalAccount,
)
from .eligibility import eligibility_reasons


APPLICATION_STATUSES = [
    ("Applied", "Applied"),
    ("Shortlisted", "Shortlisted"),
    ("Interview", "Interview"),
    ("Selected", "Selected"),
    ("Rejected", "Rejected"),
    ("Withdrawn", "Withdrawn"),
]
SELECTION_STATUSES = [("Selected", "Selected"), ("Rejected", "Rejected"), ("Waitlisted", "Waitlisted")]
OFFER_STATUSES = [("Issued", "Issued"), ("Accepted", "Accepted"), ("Declined", "Declined"), ("Joined", "Joined"), ("Withdrawn", "Withdrawn")]


class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = [
            "roll_no", "registration_no", "student_name", "email", "phone", "department",
            "admission_year", "graduation_year", "cgpa", "backlogs", "placement_status",
        ]
        widgets = {
            "cgpa": forms.NumberInput(attrs={"step": "0.01", "min": "0", "max": "10"}),
            "admission_year": forms.NumberInput(attrs={"min": "2000", "max": "2100"}),
            "graduation_year": forms.NumberInput(attrs={"min": "2000", "max": "2100"}),
            "backlogs": forms.NumberInput(attrs={"min": "0"}),
        }


class StudentPortalAccessForm(forms.Form):
    password = forms.CharField(
        label="Temporary password",
        min_length=12,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="Use at least 12 characters. Give this temporary password to the student securely.",
    )
    confirm_password = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        confirm_password = cleaned.get("confirm_password")
        if password and confirm_password and password != confirm_password:
            self.add_error("confirm_password", "The passwords do not match.")
        if password:
            try:
                validate_password(password)
            except ValidationError as error:
                self.add_error("password", error)
        return cleaned


class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = [
            "company_name", "industry", "company_type", "headquarters", "website", "contact_person",
            "contact_email", "contact_phone", "company_status", "registered_on",
        ]
        widgets = {"registered_on": forms.DateInput(attrs={"type": "date"})}


class JobRoleForm(forms.ModelForm):
    class Meta:
        model = JobRole
        fields = [
            "company", "role_title", "job_description", "employment_type", "work_location",
            "minimum_cgpa", "maximum_backlogs", "minimum_graduation_year", "salary_package",
            "bond_required", "role_status",
        ]
        widgets = {
            "minimum_cgpa": forms.NumberInput(attrs={"step": "0.01", "min": "0", "max": "10"}),
            "maximum_backlogs": forms.NumberInput(attrs={"min": "0"}),
            "minimum_graduation_year": forms.NumberInput(attrs={"min": "2000", "max": "2100"}),
            "salary_package": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }


class PlacementDriveForm(forms.ModelForm):
    class Meta:
        model = PlacementDrive
        fields = [
            "drive_name", "academic_year", "drive_type", "registration_start", "registration_end",
            "drive_start_date", "drive_end_date", "venue", "drive_status",
        ]
        widgets = {
            "registration_start": forms.DateInput(attrs={"type": "date"}),
            "registration_end": forms.DateInput(attrs={"type": "date"}),
            "drive_start_date": forms.DateInput(attrs={"type": "date"}),
            "drive_end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("registration_start"), cleaned.get("registration_end")
        if start and end and end < start:
            self.add_error("registration_end", "Registration end must be on or after the start date.")
        start, end = cleaned.get("drive_start_date"), cleaned.get("drive_end_date")
        if start and end and end < start:
            self.add_error("drive_end_date", "Drive end must be on or after the start date.")
        return cleaned


class CompanyDriveForm(forms.ModelForm):
    class Meta:
        model = CompanyDrive
        fields = [
            "drive", "company", "registration_start", "registration_end", "eligible_departments",
            "minimum_cgpa", "maximum_backlogs", "drive_status",
        ]
        widgets = {
            "registration_start": forms.DateInput(attrs={"type": "date"}),
            "registration_end": forms.DateInput(attrs={"type": "date"}),
            "minimum_cgpa": forms.NumberInput(attrs={"step": "0.01", "min": "0", "max": "10"}),
            "maximum_backlogs": forms.NumberInput(attrs={"min": "0"}),
        }
        help_texts = {"eligible_departments": "Optional: comma-separated department codes or names."}

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("registration_start"), cleaned.get("registration_end")
        if start and end and end < start:
            self.add_error("registration_end", "Registration end must be on or after the start date.")
        return cleaned


class ApplicationForm(forms.ModelForm):
    class Meta:
        model = Application
        fields = [
            "student", "company_drive", "role", "application_date", "application_status",
            "resume_submitted", "remarks",
        ]
        widgets = {"application_date": forms.DateInput(attrs={"type": "date"})}

    application_status = forms.ChoiceField(choices=APPLICATION_STATUSES, initial="Applied")

    def clean(self):
        cleaned = super().clean()
        student = cleaned.get("student")
        company_drive = cleaned.get("company_drive")
        role = cleaned.get("role")
        self.is_eligible = False
        if not (student and company_drive and role):
            return cleaned
        if role.company_id != company_drive.company_id:
            self.add_error("role", "Choose a role offered by the selected company drive.")
            return cleaned

        reasons = eligibility_reasons(student, company_drive, role)
        self.is_eligible = not reasons
        self.eligibility_reason = "; ".join(reasons)
        return cleaned

    def save(self, commit=True):
        application = super().save(commit=False)
        application.eligibility_status = "Eligible" if getattr(self, "is_eligible", False) else "Not Eligible"
        if commit:
            application.save()
            self.save_m2m()
        return application


class InterviewRoundForm(forms.ModelForm):
    class Meta:
        model = InterviewRound
        fields = [
            "application", "round_number", "round_name", "scheduled_date", "interview_mode",
            "interviewer_name", "score", "round_status", "feedback",
        ]
        widgets = {
            "scheduled_date": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "round_number": forms.NumberInput(attrs={"min": "1"}),
            "score": forms.NumberInput(attrs={"step": "0.01", "min": "0", "max": "100"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["scheduled_date"].input_formats = ["%Y-%m-%dT%H:%M"]


class SelectionForm(forms.ModelForm):
    selection_status = forms.ChoiceField(choices=SELECTION_STATUSES)

    class Meta:
        model = Selection
        fields = ["application", "selection_date", "selection_status", "final_score", "selected_by", "remarks"]
        widgets = {
            "selection_date": forms.DateInput(attrs={"type": "date"}),
            "final_score": forms.NumberInput(attrs={"step": "0.01", "min": "0", "max": "100"}),
        }


class OfferForm(forms.ModelForm):
    offer_status = forms.ChoiceField(choices=OFFER_STATUSES, initial="Issued")

    class Meta:
        model = Offer
        fields = ["selection", "offer_date", "joining_date", "annual_ctc", "offer_type", "offer_status", "offer_reference_no"]
        widgets = {
            "offer_date": forms.DateInput(attrs={"type": "date"}),
            "joining_date": forms.DateInput(attrs={"type": "date"}),
            "annual_ctc": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        selections = Selection.objects.all().order_by("-selection_date")
        if not self.instance.pk:
            selections = selections.filter(offer__isnull=True)
        self.fields["selection"].queryset = selections

    def clean(self):
        cleaned = super().clean()
        offer_date, joining_date = cleaned.get("offer_date"), cleaned.get("joining_date")
        if offer_date and joining_date and joining_date < offer_date:
            self.add_error("joining_date", "Joining date must be on or after the offer date.")
        return cleaned

class SemesterPerformanceForm(forms.ModelForm):
    class Meta:
        model = SemesterPerformance
        fields = ["academic_year", "semester", "sgpa", "cumulative_cgpa", "backlogs", "notes"]
        widgets = {
            "semester": forms.NumberInput(attrs={"min": "1", "max": "12"}),
            "sgpa": forms.NumberInput(attrs={"min": "0", "max": "10", "step": "0.01"}),
            "cumulative_cgpa": forms.NumberInput(attrs={"min": "0", "max": "10", "step": "0.01"}),
            "backlogs": forms.NumberInput(attrs={"min": "0"}),
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("semester") is not None and not 1 <= cleaned["semester"] <= 12:
            self.add_error("semester", "Semester must be from 1 to 12.")
        for field in ("sgpa", "cumulative_cgpa"):
            value = cleaned.get(field)
            if value is not None and not 0 <= value <= 10:
                self.add_error(field, "GPA must be between 0 and 10.")
        return cleaned

    def clean_academic_year(self):
        value = self.cleaned_data["academic_year"].strip()
        import re
        if not re.fullmatch(r"20\d{2}-\d{2}", value):
            raise ValidationError("Enter an academic year like 2025-26.")
        start, end = map(int, value.split("-"))
        if end != (start + 1) % 100:
            raise ValidationError("The academic year must cover two consecutive years, for example 2025-26.")
        return value


class InterviewCategoryScoreForm(forms.ModelForm):
    class Meta:
        model = InterviewCategoryScore
        fields = ["category", "score", "feedback", "visible_to_student"]
        widgets = {"score": forms.NumberInput(attrs={"min": "0", "max": "100", "step": "0.1"})}


    def clean_score(self):
        value = self.cleaned_data["score"]
        if not 0 <= value <= 100:
            raise ValidationError("Interview score must be between 0 and 100.")
        return value


class PortalReminderForm(forms.Form):
    student = forms.ModelChoiceField(queryset=Student.objects.select_related("department").order_by("roll_no"))
    reminder_type = forms.ChoiceField(choices=PortalReminder.TYPES, initial="Follow-up")
    title = forms.CharField(max_length=120)
    message = forms.CharField(max_length=500, required=False, widget=forms.Textarea(attrs={"rows": 3}))
    due_at = forms.DateTimeField(widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"), input_formats=["%Y-%m-%dT%H:%M"])

    def save(self, *, actor=None):
        student = self.cleaned_data["student"]
        return PortalReminder.objects.create(
            student_id=student.student_id,
            reminder_type=self.cleaned_data["reminder_type"],
            title=self.cleaned_data["title"],
            message=self.cleaned_data["message"],
            due_at=self.cleaned_data["due_at"],
            created_by=actor,
        )


class StudentDocumentForm(forms.ModelForm):
    document = forms.FileField(validators=[FileExtensionValidator(["pdf", "doc", "docx"])])

    class Meta:
        model = StudentDocument
        fields = ["document"]

    def clean_document(self):
        uploaded = self.cleaned_data["document"]
        if uploaded.size > 10 * 1024 * 1024:
            raise ValidationError("The file must be 10 MB or smaller.")
        return uploaded



class StudentPasswordResetForm(PasswordResetForm):
    """Only issue student reset links for accounts explicitly provisioned to students."""
    def get_users(self, email):
        for user in super().get_users(email):
            if StudentPortalAccount.objects.filter(user_id=user.pk).exists():
                yield user
