import csv
import io
import json
import mimetypes
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction, connection
from django.http import FileResponse, HttpResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import InterviewCategoryScoreForm, PortalReminderForm, SemesterPerformanceForm, StudentDocumentForm
from .models import (
    Application, CompanyDrive, Department, InterviewCategoryScore, InterviewRound, Offer,
    OfferResponseDeadline, PlacementStatusHistory, PortalReminder, RoleSkillRequirement,
    Selection, SemesterPerformance, Student, StudentDocument,
)
from .views import _open_opportunities, student_only

STAFF_ONLY = staff_member_required(login_url="/admin/login/")


def _skill_records(student):
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT sk.skill_name, ss.proficiency_level FROM student_skills ss
               JOIN skills sk ON sk.skill_id = ss.skill_id WHERE ss.student_id = %s""",
            [student.student_id],
        )
        rows = cursor.fetchall()
    ranks = {"beginner": 1, "basic": 1, "novice": 1, "intermediate": 2, "proficient": 2, "advanced": 3, "expert": 4}
    return {name.strip().casefold(): (name, level, ranks.get((level or "").casefold(), 0)) for name, level in rows}


@STAFF_ONLY
def semester_record_add(request, student_id):
    student = get_object_or_404(Student.objects.select_related("department"), pk=student_id)
    form = SemesterPerformanceForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        record = form.save(commit=False)
        record.student_id = student.student_id
        try:
            with transaction.atomic():
                record.save()
                latest = SemesterPerformance.objects.filter(student_id=student.student_id).order_by("-academic_year", "-semester").first()
                Student.objects.filter(pk=student.student_id).update(cgpa=latest.cumulative_cgpa, backlogs=latest.backlogs)
        except IntegrityError:
            form.add_error(None, "A record for that academic year and semester already exists.")
        else:
            messages.success(request, "Semester record saved and the current academic snapshot updated.")
            return redirect("student_performance", student_id=student.student_id)
    return render(request, "placements/form.html", {
        "title": f"Add semester record · {student.student_name}", "form": form,
        "cancel_href": f"/students/{student.student_id}/performance/",
        "form_note": "Enter verified term results. GPA values must be from 0 to 10.",
    })


@STAFF_ONLY
def interview_scorecard(request, round_id):
    interview = get_object_or_404(
        InterviewRound.objects.select_related("application__student", "application__company_drive__company", "application__role"),
        pk=round_id,
    )
    instance = None
    if request.method == "POST":
        instance = InterviewCategoryScore.objects.filter(
            interview_round_id=interview.round_id, category=request.POST.get("category", "")
        ).first()
    form = InterviewCategoryScoreForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        score = form.save(commit=False)
        score.interview_round_id = interview.round_id
        score.updated_by = request.user
        try:
            score.save()
        except IntegrityError:
            form.add_error(None, "That category already has a score for this round.")
        else:
            messages.success(request, "Scorecard saved. Student visibility follows the release checkbox.")
            return redirect("student_performance", student_id=interview.application.student_id)
    return render(request, "placements/form.html", {
        "title": f"Interview scorecard · {interview.round_name}", "form": form,
        "cancel_href": "/interviews/",
        "form_note": f"{interview.application.student.student_name} · {interview.application.company_drive.company.company_name} · score out of 100.",
    })


@STAFF_ONLY
def reminder_add(request):
    form = PortalReminderForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save(actor=request.user)
        messages.success(request, "Reminder added to the student portal.")
        return redirect("dashboard")
    return render(request, "placements/form.html", {
        "title": "Create student reminder", "form": form, "cancel_href": "/office/",
        "form_note": "Creates an in-portal reminder only; it does not send an email or SMS.",
    })


@student_only
@require_POST
def reminder_mark_read(request, reminder_id):
    PortalReminder.objects.filter(
        pk=reminder_id, student_id=request.student_record.student_id, read_at__isnull=True
    ).update(read_at=timezone.now())
    return redirect("student_dashboard")


def student_reminders(student):
    now = timezone.now()
    items = list(PortalReminder.objects.filter(
        student_id=student.student_id, read_at__isnull=True, due_at__gte=now - timedelta(days=2)
    ).order_by("due_at")[:10])
    for interview in InterviewRound.objects.filter(
        application__student=student, scheduled_date__gte=now, scheduled_date__lte=now + timedelta(days=30)
    ).select_related("application__company_drive__company", "application__role"):
        items.append({
            "id": None, "reminder_type": "Interview",
            "title": f"Interview · {interview.application.company_drive.company.company_name}",
            "message": f"{interview.round_name} · {interview.application.role.role_title}",
            "due_at": interview.scheduled_date, "read_at": None,
        })
    for deadline in OfferResponseDeadline.objects.filter(
        response_deadline__gte=now, response_deadline__lte=now + timedelta(days=30)
    ):
        offer = Offer.objects.filter(
            pk=deadline.offer_id, selection__application__student=student
        ).select_related("selection__application__company_drive__company", "selection__application__role").first()
        if offer and offer.offer_status.casefold() not in {"accepted", "declined", "joined", "withdrawn"}:
            items.append({
                "id": None, "reminder_type": "Offer",
                "title": f"Offer response · {offer.selection.application.company_drive.company.company_name}",
                "message": f"Respond by {deadline.response_deadline:%d %b %Y %H:%M}",
                "due_at": deadline.response_deadline, "read_at": None,
            })
    for drive in CompanyDrive.objects.filter(drive_status__iexact="Open").select_related("company", "drive"):
        close_date = drive.registration_end or drive.drive.registration_end or drive.drive.drive_end_date
        if not close_date or not now.date() <= close_date <= (now + timedelta(days=14)).date():
            continue
        if not Application.objects.filter(student=student, company_drive=drive).exists():
            items.append({
                "id": None, "reminder_type": "Deadline",
                "title": f"Registration closes · {drive.company.company_name}",
                "message": drive.drive.drive_name,
                "due_at": datetime.combine(close_date, datetime.min.time()),
                "read_at": None,
            })
    return sorted(items, key=lambda item: item["due_at"])[:12]


@STAFF_ONLY
def student_document_upload(request, student_id):
    student = get_object_or_404(Student, pk=student_id)
    form = StudentDocumentForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        document = form.save(commit=False)
        document.student_id = student.student_id
        document.original_name = os.path.basename(form.cleaned_data["document"].name)[:255]
        document.save()
        messages.success(request, "Private student document uploaded.")
        return redirect("student_detail", student_id=student.student_id)
    return render(request, "placements/form.html", {
        "title": f"Upload private document · {student.student_name}", "form": form,
        "cancel_href": f"/students/{student.student_id}/",
        "form_note": "PDF, DOC, or DOCX only, up to 10 MB. Files are served through a permission-checked download.",
    })


@login_required(login_url="student_login")
def student_document_download(request, document_id):
    document = get_object_or_404(StudentDocument, pk=document_id)
    if not request.user.is_staff:
        account = getattr(request.user, "student_portal_account", None)
        if account is None or account.student_id != document.student_id:
            raise Http404
    name = os.path.basename(document.original_name)
    return FileResponse(
        document.document.open("rb"), as_attachment=True, filename=name,
        content_type=mimetypes.guess_type(name)[0] or "application/octet-stream",
    )


@STAFF_ONLY
@require_POST
def student_account_status(request, student_id):
    from .models import StudentPortalAccount
    student = get_object_or_404(Student, pk=student_id)
    account = get_object_or_404(StudentPortalAccount.objects.select_related("user"), student_id=student.student_id)
    if account.user.is_staff or account.user.is_superuser:
        messages.error(request, "Staff accounts cannot be disabled through the student workflow.")
    else:
        account.user.is_active = not account.user.is_active
        account.user.save(update_fields=["is_active"])
        messages.success(request, f"Student access {'enabled' if account.user.is_active else 'disabled'}; records remain preserved.")
    return redirect("student_detail", student_id=student.student_id)


@STAFF_ONLY
def student_import_export(request):
    fields = ["roll_no", "registration_no", "student_name", "email", "phone", "department_code", "admission_year", "graduation_year", "cgpa", "backlogs"]
    if request.method == "GET" and request.GET.get("template") == "1":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="students-import-template.csv"'
        csv.writer(response).writerow(fields)
        return response
    if request.method == "GET" and request.GET.get("export") == "students.csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="students.csv"'
        writer = csv.writer(response)
        writer.writerow(fields)
        for row in Student.objects.select_related("department").order_by("roll_no"):
            writer.writerow([row.roll_no, row.registration_no or "", row.student_name, row.email, row.phone or "", row.department.department_code, row.admission_year, row.graduation_year, row.cgpa, row.backlogs])
        return response
    errors, imported = [], 0
    if request.method == "POST":
        upload = request.FILES.get("file")
        if not upload or not upload.name.lower().endswith(".csv") or upload.size > 5 * 1024 * 1024:
            errors.append("Upload a CSV file no larger than 5 MB.")
        else:
            try:
                reader = csv.DictReader(io.StringIO(upload.read().decode("utf-8-sig")))
                if reader.fieldnames != fields:
                    errors.append("CSV headers must match the template order exactly.")
                else:
                    valid, rolls, emails, regs = [], set(), set(), set()
                    seen_rolls = set(Student.objects.values_list("roll_no", flat=True))
                    seen_emails = {e.casefold() for e in Student.objects.values_list("email", flat=True)}
                    seen_regs = set(Student.objects.exclude(registration_no__isnull=True).values_list("registration_no", flat=True))
                    departments = {d.department_code.casefold(): d for d in Department.objects.all()}
                    for line, row in enumerate(reader, start=2):
                        roll = (row.get("roll_no") or "").strip()
                        email = (row.get("email") or "").strip().casefold()
                        reg = (row.get("registration_no") or "").strip()
                        if not roll or not row.get("student_name", "").strip() or "@" not in email:
                            errors.append(f"Row {line}: valid roll number, name, and email are required.")
                            continue
                        if roll in seen_rolls or roll in rolls or email in seen_emails or email in emails or (reg and (reg in seen_regs or reg in regs)):
                            errors.append(f"Row {line}: duplicate roll number, email, or registration number.")
                            continue
                        dept = departments.get((row.get("department_code") or "").strip().casefold())
                        if dept is None:
                            errors.append(f"Row {line}: department_code must match a department in the database.")
                            continue
                        try:
                            admission, graduation = int(row["admission_year"]), int(row["graduation_year"])
                            cgpa, backlogs = float(row["cgpa"]), int(row["backlogs"])
                            if not 2000 <= admission <= 2100 or not admission <= graduation <= 2100 or not 0 <= cgpa <= 10 or backlogs < 0:
                                raise ValueError
                        except (ValueError, TypeError, KeyError):
                            errors.append(f"Row {line}: years, CGPA (0–10), or backlog count are invalid.")
                            continue
                        valid.append(Student(
                            roll_no=roll, registration_no=reg or None,
                            student_name=row["student_name"].strip(), email=email,
                            phone=(row.get("phone") or "").strip() or None,
                            department=dept, admission_year=admission, graduation_year=graduation,
                            cgpa=cgpa, backlogs=backlogs, placement_status="Not Placed",
                        ))
                        rolls.add(roll); emails.add(email)
                        if reg: regs.add(reg)
                    if not valid and not errors: errors.append("The CSV contains no student rows.")
                    if not errors:
                        try:
                            with transaction.atomic(): Student.objects.bulk_create(valid)
                        except IntegrityError:
                            errors.append("Database duplicate check failed; no rows were imported.")
                        else: imported = len(valid)
            except (UnicodeDecodeError, csv.Error):
                errors.append("This is not a valid UTF-8 CSV file.")
        if imported: messages.success(request, f"Imported {imported} student record(s).")
    return render(request, "placements/student_import.html", {"errors": errors, "imported": imported, "fields": fields})


@STAFF_ONLY
def status_history(request):
    events = PlacementStatusHistory.objects.select_related("actor").order_by("-changed_at")
    department, year = request.GET.get("department", ""), request.GET.get("academic_year", "")
    if department or year:
        students = Student.objects.all()
        if department.isdigit(): students = students.filter(department_id=int(department))
        elif department: students = students.none()
        if year:
            try: students = students.filter(graduation_year=int(year))
            except ValueError: students = students.none()
        events = events.filter(student_id__in=students.values_list("student_id", flat=True))
    return render(request, "placements/status_history.html", {
        "events": events[:300], "departments": Department.objects.all(),
        "selected_department": department, "academic_year": year,
    })


def _anonymous_metrics(student):
    semesters = list(SemesterPerformance.objects.filter(student_id=student.student_id).order_by("academic_year", "semester").values("semester", "sgpa", "cumulative_cgpa", "backlogs"))
    applications = Application.objects.filter(student=student)
    interview_scores = list(InterviewRound.objects.filter(application__student=student, score__isnull=False).values_list("score", flat=True))
    released_scores = list(InterviewCategoryScore.objects.filter(
        interview_round_id__in=InterviewRound.objects.filter(application__student=student).values_list("round_id", flat=True),
        visible_to_student=True,
    ).values_list("category", "score"))
    totals = {}
    for category, score in released_scores: totals.setdefault(category, []).append(float(score))
    return {
        "academic": {"current_cgpa": float(student.cgpa), "current_backlogs": student.backlogs, "semesters": [{"number": x["semester"], "sgpa": float(x["sgpa"]), "cgpa": float(x["cumulative_cgpa"]), "backlogs": x["backlogs"]} for x in semesters]},
        "placement": {"applications": applications.count(), "selected": Selection.objects.filter(application__student=student, selection_status__iexact="Selected").count(), "rejected": applications.filter(application_status__iexact="Rejected").count(), "offers": Offer.objects.filter(selection__application__student=student).count(), "eligible_open_roles": sum(1 for item in _open_opportunities(student) if item["eligible"])},
        "interviews": {"scored_rounds": len(interview_scores), "average_score": round(sum(float(v) for v in interview_scores)/len(interview_scores), 1) if interview_scores else None, "released_category_averages": {key: round(sum(vals)/len(vals), 1) for key, vals in totals.items()}},
    }


def _generate_ai_report(metrics):
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key: return None, "AI is optional and not configured. Add OPENAI_API_KEY to .env to enable it."
    payload = {
        "model": os.getenv("OPENAI_MODEL", "gpt-5-mini"),
        "store": False, "max_output_tokens": 550,
        "input": [
            {"role": "developer", "content": "You coach students using only the anonymized aggregate metrics supplied. Give a concise evidence-based progress summary and up to three practical preparation actions. Never predict hiring outcomes, rank employability, or make hiring decisions. Do not invent data; state when it is insufficient. Do not ask for personal information."},
            {"role": "user", "content": json.dumps(metrics, separators=(",", ":"))},
        ],
    }
    req = urllib.request.Request("https://api.openai.com/v1/responses", data=json.dumps(payload).encode("utf-8"), headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as response: body = json.loads(response.read().decode("utf-8"))
        text = body.get("output_text", "").strip()
        if not text:
            text = "\n".join(part.get("text", "") for item in body.get("output", []) for part in item.get("content", []) if part.get("type") == "output_text").strip()
        return (text, None) if text else (None, "AI service returned no report text.")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return None, f"AI request failed ({type(exc).__name__}); no portal data was changed."


@student_only
@require_POST
def student_ai_insight(request):
    student = request.student_record
    insight, error = _generate_ai_report(_anonymous_metrics(student))
    return render(request, "placements/student_ai_insight.html", {"student": student, "insight": insight, "error": error})


@STAFF_ONLY
@require_POST
def staff_ai_insight(request, student_id):
    student = get_object_or_404(Student.objects.select_related("department"), pk=student_id)
    insight, error = _generate_ai_report(_anonymous_metrics(student))
    return render(request, "placements/ai_insight.html", {"student": student, "insight": insight, "error": error})


@student_only
def student_document_upload_self(request):
    student = request.student_record
    form = StudentDocumentForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        record = form.save(commit=False)
        record.student_id = student.student_id
        record.original_name = os.path.basename(form.cleaned_data["document"].name)[:255]
        record.save()
        messages.success(request, "Your private document was uploaded to your profile.")
        return redirect("student_dashboard")
    return render(request, "placements/form.html", {
        "title": "Upload resume or document", "form": form,
        "cancel_href": "/student/", "form_note": "PDF, DOC, or DOCX up to 10 MB. Only you and placement staff can access it.",
        "is_student_form": True,
    })
