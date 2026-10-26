from datetime import date
from functools import wraps

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.db import IntegrityError, connection, transaction
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import (
    ApplicationForm,
    CompanyDriveForm,
    CompanyForm,
    InterviewRoundForm,
    JobRoleForm,
    OfferForm,
    PlacementDriveForm,
    SelectionForm,
    StudentForm,
    StudentPortalAccessForm,
)
from .eligibility import eligibility_reasons
from .models import (
    Application,
    Company,
    CompanyDrive,
    Department,
    InterviewRound,
    JobRole,
    Offer,
    PlacementDrive,
    Selection,
    Student,
    StudentPortalAccount,
    SemesterPerformance, InterviewCategoryScore, PlacementStatusHistory, StudentDocument, RoleSkillRequirement,
)
from .report_queries import load_report_queries


STAFF_LOGIN = "/admin/login/"
STAFF_ONLY = staff_member_required(login_url=STAFF_LOGIN)


def student_only(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if request.user.is_staff:
            return redirect("dashboard")
        account = StudentPortalAccount.objects.filter(user_id=request.user.pk).first()
        if account is None:
            logout(request)
            messages.error(request, "This login is not linked to a student record. Contact the placement office.")
            return redirect("student_login")
        student = Student.objects.select_related("department").filter(pk=account.student_id).first()
        if student is None:
            logout(request)
            messages.error(request, "Your student profile is unavailable. Contact the placement office.")
            return redirect("student_login")
        request.student_record = student
        return view_func(request, *args, **kwargs)

    return login_required(login_url="student_login")(wrapped)


def _open_opportunities(student):
    today = date.today()
    existing_applications = {
        (item.company_drive_id, item.role_id): item
        for item in Application.objects.filter(student=student)
    }
    company_drives = CompanyDrive.objects.select_related("drive", "company").filter(
        drive_status__iexact="Open", company__company_status__iexact="Active"
    ).exclude(drive__drive_status__iexact="Completed").exclude(
        drive__drive_status__iexact="Cancelled"
    ).exclude(drive__drive_status__iexact="Closed")

    opportunities = []
    for company_drive in company_drives:
        registration_start = company_drive.registration_start or company_drive.drive.registration_start
        registration_end = (
            company_drive.registration_end
            or company_drive.drive.registration_end
            or company_drive.drive.drive_end_date
        )
        if registration_start and registration_start > today:
            continue
        if registration_end and registration_end < today:
            continue

        roles = JobRole.objects.filter(
            company_id=company_drive.company_id, role_status__iexact="Open"
        ).order_by("role_title")
        for role in roles:
            reasons = eligibility_reasons(student, company_drive, role)
            skill_requirements = list(RoleSkillRequirement.objects.filter(role_id=role.role_id).order_by("skill_name"))
            minimum_cgpa_values = [
                value for value in (role.minimum_cgpa, company_drive.minimum_cgpa)
                if value is not None
            ]
            next_steps = []
            for reason in reasons:
                lowered = reason.casefold()
                if "cgpa" in lowered:
                    next_steps.append("Review the current academic record with the placement office; eligibility uses the verified CGPA on file.")
                elif "backlog" in lowered:
                    next_steps.append("Work with your academic adviser on the recorded backlog(s), then ask the office to refresh your profile.")
                elif "skill" in lowered:
                    next_steps.append("Ask the placement office to update your recorded skill evidence after you have relevant coursework or project experience.")
                elif "department" in lowered or "graduation year" in lowered:
                    next_steps.append("Check other open roles whose published department and graduation criteria match your profile.")
            opportunities.append({
                "company_drive": company_drive,
                "role": role,
                "eligible": not reasons,
                "reasons": reasons,
                "next_steps": list(dict.fromkeys(next_steps)),
                "required_cgpa": max(minimum_cgpa_values) if minimum_cgpa_values else None,
                "maximum_backlogs": min(role.maximum_backlogs, company_drive.maximum_backlogs),
                "skill_requirements": skill_requirements,
                "application": existing_applications.get((company_drive.company_drive_id, role.role_id)),
            })
    return opportunities


def _records(request, *, title, eyebrow, description, headers, rows, add_url=None, actions=None, search=""):
    return render(
        request,
        "placements/records.html",
        {
            "title": title,
            "eyebrow": eyebrow,
            "description": description,
            "headers": headers,
            "rows": rows,
            "add_url": add_url,
            "actions": actions or [],
            "search": search,
            "departments": Department.objects.all() if request.resolver_match.url_name in {"students", "applications"} else None,
            "selected_department": request.GET.get("department", ""),
            "academic_years": list(PlacementDrive.objects.order_by().values_list("academic_year", flat=True).distinct().order_by("academic_year")) if request.resolver_match.url_name == "applications" else [],
            "selected_academic_year": request.GET.get("academic_year", ""),
            "graduation_years": list(Student.objects.order_by().values_list("graduation_year", flat=True).distinct().order_by("graduation_year")) if request.resolver_match.url_name == "students" else [],
            "selected_graduation_year": request.GET.get("graduation_year", ""),
        },
    )


def _record_form(request, form_class, title, success_url, *, extra_context=None):
    form = form_class(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                record = form.save()
                if isinstance(record, Application):
                    PlacementStatusHistory.objects.create(student_id=record.student_id, record_type="Application", record_id=record.pk, field_name="application_status", old_value="", new_value=record.application_status or "", actor=request.user)
                elif isinstance(record, Selection):
                    PlacementStatusHistory.objects.create(student_id=record.application.student_id, record_type="Selection", record_id=record.pk, field_name="selection_status", old_value="", new_value=record.selection_status or "", actor=request.user)
                elif isinstance(record, Offer):
                    PlacementStatusHistory.objects.create(student_id=record.selection.application.student_id, record_type="Offer", record_id=record.pk, field_name="offer_status", old_value="", new_value=record.offer_status or "", actor=request.user)
                if isinstance(record, Offer) and record.offer_status.casefold() in {"accepted", "joined"}:
                    Student.objects.filter(pk=record.selection.application.student_id).update(placement_status="Placed")
        except IntegrityError:
            form.add_error(None, "This record conflicts with an existing entry. Check the selected student, drive, role, or status.")
        else:
            if isinstance(record, Application):
                status = "eligible" if record.eligibility_status == "Eligible" else "not eligible"
                messages.success(request, f"Application saved. The student is {status} for this role.")
            else:
                messages.success(request, f"{title} saved successfully.")
            return redirect(success_url)
    context = {"title": title, "form": form, "cancel_url": success_url}
    if extra_context:
        context.update(extra_context)
    return render(request, "placements/form.html", context)


def portal_home(request):
    is_staff_user = request.user.is_authenticated and (
        request.user.is_staff or request.user.is_superuser
    )
    student_account = None
    if request.user.is_authenticated and not is_staff_user:
        student_account = (
            StudentPortalAccount.objects.select_related("student")
            .filter(user_id=request.user.pk)
            .first()
        )
    return render(request, "placements/portal_home.html", {
        "is_staff_user": is_staff_user,
        "student_account": student_account,
    })

@STAFF_ONLY
def dashboard(request):
    student_count = Student.objects.count()
    placed_count = Student.objects.filter(placement_status__iexact="Placed").count()
    departments = Department.objects.annotate(
        student_count=Count("students__student_id", distinct=True),
        placed_count=Count(
            "students__student_id",
            filter=Q(students__placement_status__iexact="Placed"),
            distinct=True,
        ),
    ).order_by("department_name")
    department_rows = [
        {
            "name": department.department_name,
            "placed": department.placed_count,
            "total": department.student_count,
            "percent": round(department.placed_count * 100 / department.student_count)
            if department.student_count else 0,
        }
        for department in departments
    ]
    with connection.cursor() as cursor:
        cursor.execute("SELECT DISTINCT student_id FROM student_skills")
        students_with_skills = [row[0] for row in cursor.fetchall()]
    follow_up_students = Student.objects.filter(
        Q(phone__isnull=True) | Q(phone="") | Q(placement_status__isnull=True) | Q(placement_status="")
    ).exclude(student_id__in=students_with_skills).select_related("department").order_by("graduation_year", "roll_no")[:8]
    context = {
        "student_count": student_count,
        "placed_count": placed_count,
        "placement_rate": round(placed_count * 100 / student_count) if student_count else 0,
        "company_count": Company.objects.count(),
        "open_roles": JobRole.objects.filter(role_status__iexact="Open").count(),
        "application_count": Application.objects.count(),
        "average_ctc": Offer.objects.filter(
            annual_ctc__isnull=False
        ).aggregate(value=Avg("annual_ctc"))["value"],
        "department_rows": department_rows,
        "recent_applications": Application.objects.select_related(
            "student", "company_drive__company", "role"
        ).order_by("-application_date", "-application_id")[:6],
        "upcoming_interviews": InterviewRound.objects.filter(scheduled_date__date__gte=date.today()).select_related("application__student", "application__company_drive__company", "application__role").order_by("scheduled_date")[:8],
        "follow_up_students": follow_up_students,
    }
    return render(request, "placements/dashboard.html", context)


@STAFF_ONLY
def students(request):
    queryset = Student.objects.select_related("department").annotate(
        application_count=Count("applications__application_id", distinct=True),
        offer_count=Count("applications__selection__offer__offer_id", distinct=True),
    )
    search = request.GET.get("q", "").strip()
    department_id = request.GET.get("department", "")
    graduation_year = request.GET.get("graduation_year", "")
    if search:
        queryset = queryset.filter(
            Q(student_name__icontains=search)
            | Q(roll_no__icontains=search)
            | Q(email__icontains=search)
        )
    if department_id.isdigit():
        queryset = queryset.filter(department_id=int(department_id))
    elif department_id:
        queryset = queryset.none()
    if graduation_year.isdigit():
        queryset = queryset.filter(graduation_year=int(graduation_year))
    rows = [
        [student.roll_no, student.student_name, student.department.department_name, student.cgpa,
         student.backlogs, student.application_count, student.offer_count, student.placement_status,
         reverse("student_detail", args=[student.student_id])]
        for student in queryset.order_by("roll_no")
    ]
    return render(request, "placements/records.html", {
        "title": "Students", "eyebrow": "Student directory",
        "description": "Academic profiles, application activity, offers, and placement status.",
        "headers": ["Roll number", "Student", "Department", "CGPA", "Backlogs",
                    "Applications", "Offers", "Placement", "Profile"],
        "rows": rows, "add_url": "student_add", "search": search,
        "actions": [{"url": reverse("student_import_export"), "label": "CSV import / export"}, {"url": reverse("status_history"), "label": "Status history"}],
        "departments": Department.objects.all(), "selected_department": department_id,
        "graduation_years": Student.objects.order_by().values_list("graduation_year", flat=True).distinct().order_by("graduation_year"),
        "selected_graduation_year": graduation_year,
    })


@STAFF_ONLY
def student_add(request):
    return _record_form(request, StudentForm, "Add student", "students")


@STAFF_ONLY
def student_detail(request, student_id):
    student = get_object_or_404(Student.objects.select_related("department"), pk=student_id)
    applications = Application.objects.filter(student=student).select_related(
        "company_drive__company", "company_drive__drive", "role", "selection__offer"
    ).order_by("-application_date", "-application_id")
    offers = Offer.objects.filter(selection__application__student=student).select_related(
        "selection__application__company_drive__company",
        "selection__application__role",
    ).order_by("-offer_date", "-offer_id")
    opportunities = _open_opportunities(student)
    portal_account = StudentPortalAccount.objects.select_related("user").filter(
        student_id=student.student_id
    ).first()

    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT sk.skill_name, ss.proficiency_level, ss.years_of_experience
               FROM student_skills AS ss INNER JOIN skills AS sk ON sk.skill_id = ss.skill_id
               WHERE ss.student_id = %s ORDER BY sk.skill_name""",
            [student.student_id],
        )
        skills = [{"name": row[0], "level": row[1], "experience": row[2]} for row in cursor.fetchall()]

    return render(request, "placements/student_detail.html", {
        "student": student,
        "applications": applications,
        "application_count": applications.count(),
        "offers": offers,
        "offer_count": offers.count(),
        "eligible_opportunity_count": sum(1 for item in opportunities if item["eligible"]),
        "opportunities": opportunities,
        "skills": skills,
        "portal_account": portal_account,
        "semester_records": SemesterPerformance.objects.filter(student_id=student.student_id).order_by("-academic_year", "-semester"),
        "private_documents": StudentDocument.objects.filter(student_id=student.student_id),
        "status_history": PlacementStatusHistory.objects.filter(student_id=student.student_id).select_related("actor")[:20],
    })


@STAFF_ONLY
def student_portal_access(request, student_id):
    student = get_object_or_404(Student, pk=student_id)
    portal_account = StudentPortalAccount.objects.select_related("user").filter(
        student_id=student.student_id
    ).first()
    form = StudentPortalAccessForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        User = get_user_model()
        if portal_account:
            user = portal_account.user
            if user.is_staff or user.is_superuser:
                form.add_error(None, "This login is reserved for staff and cannot be used as a student account.")
            elif User.objects.filter(username=student.roll_no).exclude(pk=user.pk).exists():
                form.add_error(None, "A login with this roll number already exists. Resolve it in Django admin first.")
            else:
                user.username = student.roll_no
                user.email = student.email
                user.set_password(form.cleaned_data["password"])
                user.is_active = True
                user.save(update_fields=["username", "email", "password", "is_active"])
                messages.success(request, f"Portal password reset for {student.student_name}.")
                return redirect("student_detail", student_id=student.student_id)
        elif User.objects.filter(username=student.roll_no).exists():
            form.add_error(None, "A login with this roll number already exists. Resolve it in Django admin first.")
        else:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=student.roll_no,
                    email=student.email,
                    password=form.cleaned_data["password"],
                    is_staff=False,
                    is_superuser=False,
                    is_active=True,
                )
                StudentPortalAccount.objects.create(user=user, student_id=student.student_id)
            messages.success(request, f"Student portal access created for {student.student_name}.")
            return redirect("student_detail", student_id=student.student_id)

    return render(request, "placements/student_access.html", {
        "student": student,
        "portal_account": portal_account,
        "form": form,
    })


@require_POST
def portal_logout(request):
    logout(request)
    return redirect("portal_home")

def student_login(request):
    if request.user.is_authenticated:
        if request.user.is_staff or request.user.is_superuser:
            messages.info(request, "You are signed in to the placement office. Sign out first to switch to a student account.")
            return redirect("portal_home")
        if StudentPortalAccount.objects.filter(user_id=request.user.pk).exists():
            return redirect("student_dashboard")
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        if user.is_staff or user.is_superuser:
            form.add_error(None, "Staff accounts must sign in through the placement office login.")
        elif not StudentPortalAccount.objects.filter(user=user).exists():
            form.add_error(None, "Student portal access has not been enabled. Contact the placement office.")
        else:
            login(request, user)
            return redirect("student_dashboard")
    return render(request, "placements/student_login.html", {"form": form})


@student_only
def student_dashboard(request):
    student = request.student_record
    applications = Application.objects.filter(student=student).select_related(
        "company_drive__company", "company_drive__drive", "role", "selection__offer"
    ).prefetch_related("interview_rounds").order_by("-application_date", "-application_id")
    offers = Offer.objects.filter(selection__application__student=student).select_related(
        "selection__application__company_drive__company",
        "selection__application__role",
    ).order_by("-offer_date", "-offer_id")
    opportunities = _open_opportunities(student)
    return render(request, "placements/student_dashboard.html", {
        "student": student,
        "applications": applications,
        "offers": offers,
        "opportunities": opportunities,
        "application_count": applications.count(),
        "offer_count": offers.count(),
        "eligible_opportunity_count": sum(1 for item in opportunities if item["eligible"]),
        "student_reminders": __import__("placements.enhancements", fromlist=["student_reminders"]).student_reminders(student),
        "semester_records": SemesterPerformance.objects.filter(student_id=student.student_id).order_by("academic_year", "semester"),
        "private_documents": StudentDocument.objects.filter(student_id=student.student_id),
    })


def _student_performance_report_data(student, *, include_private_feedback=False):
    """Build a factual recruitment score trend and dated activity trail for one student."""
    scored_rounds = list(
        InterviewRound.objects.filter(
            application__student=student,
            score__isnull=False,
            scheduled_date__isnull=False,
        )
        .select_related("application__company_drive__company", "application__role")
        .order_by("scheduled_date", "round_id")
    )[-12:]
    trend_points = []
    point_count = len(scored_rounds)
    for index, interview in enumerate(scored_rounds):
        x = 50 if point_count == 1 else 10 + (80 * index / (point_count - 1))
        score = float(interview.score)
        y = 90 - (max(0, min(100, score)) * 0.8)
        company = interview.application.company_drive.company.company_name
        role = interview.application.role.role_title
        trend_points.append({
            "x": f"{x:.1f}",
            "y": f"{y:.1f}",
            "score": round(score, 1),
            "date": interview.scheduled_date,
            "label": f"{company} · {role} · {interview.round_name}",
        })

    events = []
    applications = Application.objects.filter(student=student).select_related(
        "company_drive__company", "role"
    )
    for application in applications:
        company = application.company_drive.company.company_name
        events.append({
            "date": application.application_date,
            "_sort_date": application.application_date,
            "_sort_id": application.application_id,
            "kind": "Application",
            "title": f"Applied to {company}",
            "subtitle": application.role.role_title,
            "detail": f"{application.application_status} · eligibility {application.eligibility_status}",
        })

    selections = Selection.objects.filter(application__student=student).select_related(
        "application__company_drive__company", "application__role"
    )
    for selection in selections:
        application = selection.application
        events.append({
            "date": selection.selection_date,
            "_sort_date": selection.selection_date,
            "_sort_id": selection.selection_id,
            "kind": "Selection",
            "title": f"Selection decision · {application.company_drive.company.company_name}",
            "subtitle": application.role.role_title,
            "detail": selection.selection_status,
        })

    interview_events = InterviewRound.objects.filter(application__student=student).select_related(
        "application__company_drive__company", "application__role"
    )
    for interview in interview_events:
        event_date = interview.scheduled_date.date() if interview.scheduled_date else None
        application = interview.application
        detail = interview.round_status
        if interview.score is not None:
            detail += f" · score {float(interview.score):.1f}/100"
        events.append({
            "date": event_date,
            "_sort_date": event_date or date.min,
            "_sort_id": interview.round_id,
            "kind": "Interview",
            "title": f"{interview.round_name} · {application.company_drive.company.company_name}",
            "subtitle": application.role.role_title,
            "detail": detail,
        })

    offers = Offer.objects.filter(selection__application__student=student).select_related(
        "selection__application__company_drive__company",
        "selection__application__role",
    )
    for offer in offers:
        application = offer.selection.application
        detail = offer.offer_status
        if offer.annual_ctc is not None:
            detail += f" · annual CTC ₹{float(offer.annual_ctc):,.0f}"
        events.append({
            "date": offer.offer_date,
            "_sort_date": offer.offer_date,
            "_sort_id": offer.offer_id,
            "kind": "Offer",
            "title": f"Offer · {application.company_drive.company.company_name}",
            "subtitle": application.role.role_title,
            "detail": detail,
        })

    activity_timeline = sorted(
        events, key=lambda item: (item["_sort_date"], item["_sort_id"]), reverse=True
    )[:12]
    for event in activity_timeline:
        event.pop("_sort_date")
        event.pop("_sort_id")

    semester_records = list(SemesterPerformance.objects.filter(student_id=student.student_id).order_by("academic_year", "semester"))
    semester_points = []
    total = len(semester_records)
    for index, record in enumerate(semester_records):
        x = 50 if total == 1 else 10 + (80 * index / (total - 1))
        semester_points.append({
            "x": f"{x:.1f}",
            "sgpa_y": f"{90 - max(0, min(10, float(record.sgpa))) * 8:.1f}",
            "cgpa_y": f"{90 - max(0, min(10, float(record.cumulative_cgpa))) * 8:.1f}",
            "sgpa": float(record.sgpa), "cgpa": float(record.cumulative_cgpa),
            "backlogs": record.backlogs,
            "label": f"{record.academic_year} · Semester {record.semester}",
        })

    trend_rounds = list(InterviewRound.objects.filter(
        application__student=student, scheduled_date__isnull=False
    ).order_by("scheduled_date", "round_id"))
    round_positions = {item.round_id: index for index, item in enumerate(trend_rounds)}
    round_count = len(trend_rounds)
    category_scores = InterviewCategoryScore.objects.filter(
        interview_round_id__in=round_positions.keys()
    )
    if not include_private_feedback:
        category_scores = category_scores.filter(visible_to_student=True)
    grouped_category_scores = {}
    for score_record in category_scores.order_by("category", "interview_round_id"):
        index = round_positions.get(score_record.interview_round_id)
        if index is None:
            continue
        x = 50 if round_count == 1 else 10 + (80 * index / (round_count - 1))
        score_value = float(score_record.score)
        point = {
            "x": f"{x:.1f}", "y": f"{90 - max(0, min(100, score_value)) * 0.8:.1f}",
            "score": round(score_value, 1),
            "date": trend_rounds[index].scheduled_date,
            "label": f"{score_record.category} · round {score_record.interview_round_id}",
        }
        grouped_category_scores.setdefault(score_record.category, []).append(point)
    category_trends = []
    for index, (category, points) in enumerate(sorted(grouped_category_scores.items())):
        category_trends.append({
            "category": category, "color_index": index % 5, "points": points,
            "svg_points": " ".join(f"{point['x']},{point['y']}" for point in points),
        })

    return {
        "interview_trend": {
            "points": trend_points,
            "svg_points": " ".join(f"{point['x']},{point['y']}" for point in trend_points),
            "start_date": trend_points[0]["date"] if trend_points else None,
            "end_date": trend_points[-1]["date"] if trend_points else None,
        },
        "activity_timeline": activity_timeline,
        "semester_trend": {
            "points": semester_points,
            "sgpa_svg_points": " ".join(f"{point['x']},{point['sgpa_y']}" for point in semester_points),
            "cgpa_svg_points": " ".join(f"{point['x']},{point['cgpa_y']}" for point in semester_points),
        },
        "semester_trend_last_label": semester_points[-1]["label"] if semester_points else "",
        "interview_category_trends": category_trends,
    }


@student_only
def student_analytics(request):
    student = request.student_record
    applications = list(
        Application.objects.filter(student=student)
        .select_related("company_drive__company", "role")
        .order_by("-application_date", "-application_id")
    )
    application_count = len(applications)
    selection_statuses = dict(
        Selection.objects.filter(application__student=student)
        .values_list("application_id", "selection_status")
    )
    rejected_count = Application.objects.filter(student=student).filter(
        Q(application_status__iexact="Rejected")
        | Q(selection__selection_status__iexact="Rejected")
    ).distinct().count()
    selected_count = sum(
        1 for status in selection_statuses.values() if (status or "").casefold() == "selected"
    )

    offers = Offer.objects.filter(
        selection__application__student=student
    ).select_related(
        "selection__application__company_drive__company",
        "selection__application__role",
    ).order_by("-offer_date", "-offer_id")
    offer_count = offers.count()
    accepted_offer_count = offers.filter(
        Q(offer_status__iexact="Accepted") | Q(offer_status__iexact="Joined")
    ).count()

    interview_summary = InterviewRound.objects.filter(
        application__student=student
    ).aggregate(
        average=Avg("score"),
        scored_rounds=Count("round_id", filter=Q(score__isnull=False)),
        total_rounds=Count("round_id"),
    )
    interviews = InterviewRound.objects.filter(
        application__student=student
    ).select_related(
        "application__company_drive__company",
        "application__role",
    ).order_by("-scheduled_date", "-round_id")[:8]

    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT sk.skill_name, ss.proficiency_level, ss.years_of_experience
               FROM student_skills AS ss INNER JOIN skills AS sk ON sk.skill_id = ss.skill_id
               WHERE ss.student_id = %s ORDER BY sk.skill_name""",
            [student.student_id],
        )
        skills = [
            {"name": row[0], "level": row[1], "experience": row[2]}
            for row in cursor.fetchall()
        ]

    opportunities = _open_opportunities(student)
    eligible_opportunity_count = sum(1 for item in opportunities if item["eligible"])
    opportunity_count = len(opportunities)

    in_progress_count = max(application_count - selected_count - rejected_count, 0)
    outcome_rows = [
        ("Applications", application_count),
        ("Awaiting outcome", in_progress_count),
        ("Selected", selected_count),
        ("Rejected", rejected_count),
        ("Offers recorded", offer_count),
        ("Accepted or joined", accepted_offer_count),
    ]
    outcome_funnel = [
        {
            "label": label,
            "count": count,
            "percent": round(count * 100 / application_count) if application_count else 0,
        }
        for label, count in outcome_rows
    ]

    company_progress = {}
    offer_application_ids = set(
        offers.values_list("selection__application_id", flat=True)
    )
    for application in applications:
        company_name = application.company_drive.company.company_name
        row = company_progress.setdefault(company_name, {
            "name": company_name, "applications": 0, "selected": 0,
            "rejected": 0, "offers": 0,
        })
        row["applications"] += 1
        selection_status = (selection_statuses.get(application.application_id) or "").casefold()
        application_status = (application.application_status or "").casefold()
        if selection_status == "selected":
            row["selected"] += 1
        if selection_status == "rejected" or application_status == "rejected":
            row["rejected"] += 1
        if application.application_id in offer_application_ids:
            row["offers"] += 1
    company_rows = sorted(
        company_progress.values(),
        key=lambda row: (-row["applications"], row["name"].casefold()),
    )

    analysis_notes = []
    if opportunity_count:
        analysis_notes.append(
            f"You currently meet the listed criteria for {eligible_opportunity_count} of "
            f"{opportunity_count} open roles."
        )
    else:
        analysis_notes.append("There are no open roles to compare against your profile right now.")
    if application_count:
        selected_suffix = "" if selected_count == 1 else "s"
        rejected_suffix = "" if rejected_count == 1 else "s"
        analysis_notes.append(
            f"You have {selected_count} selected application{selected_suffix} and "
            f"{rejected_count} rejected application{rejected_suffix} on record."
        )
    else:
        analysis_notes.append("You have not applied to a role yet; start with an eligible open opportunity.")
    if interview_summary["average"] is None:
        analysis_notes.append("Interview analysis will appear after scored interview rounds are recorded.")
    else:
        scored_suffix = "" if interview_summary["scored_rounds"] == 1 else "s"
        analysis_notes.append(
            f"Your interview average is {interview_summary['average']:.1f} across "
            f"{interview_summary['scored_rounds']} scored round{scored_suffix}."
        )
    if not skills:
        analysis_notes.append("No skills are recorded in your profile yet. Ask the placement office to update them.")
    else:
        skill_suffix = "" if len(skills) == 1 else "s"
        analysis_notes.append(f"{len(skills)} skill{skill_suffix} recorded in your profile.")
    analysis_notes.append(
        "CGPA is a current profile snapshot; the database has no semester history for an academic trend chart."
    )
    performance_report = _student_performance_report_data(student)

    return render(request, "placements/student_analytics.html", {
        **performance_report,
        "student": student,
        "applications": applications,
        "application_count": application_count,
        "selected_count": selected_count,
        "rejected_count": rejected_count,
        "in_progress_count": in_progress_count,
        "selection_rate": round(selected_count * 100 / application_count) if application_count else None,
        "offers": offers,
        "offer_count": offer_count,
        "accepted_offer_count": accepted_offer_count,
        "interviews": interviews,
        "interview_summary": interview_summary,
        "skills": skills,
        "opportunities": opportunities,
        "eligible_opportunity_count": eligible_opportunity_count,
        "opportunity_count": opportunity_count,
        "eligibility_rate": round(eligible_opportunity_count * 100 / opportunity_count) if opportunity_count else 0,
        "outcome_funnel": outcome_funnel,
        "company_rows": company_rows,
        "analysis_notes": analysis_notes,
        "semester_records": SemesterPerformance.objects.filter(student_id=student.student_id).order_by("academic_year", "semester"),
        "released_category_scores": InterviewCategoryScore.objects.filter(interview_round_id__in=InterviewRound.objects.filter(application__student=student).values_list("round_id", flat=True), visible_to_student=True).select_related("updated_by"),
    })

@student_only
def student_applications(request):
    student = request.student_record
    applications = Application.objects.filter(student=student).select_related(
        "company_drive__company", "company_drive__drive", "role", "selection__offer"
    ).prefetch_related("interview_rounds").order_by("-application_date", "-application_id")
    return render(request, "placements/student_applications.html", {
        "student": student,
        "applications": applications,
    })


@student_only
@require_POST
def student_apply(request, company_drive_id, role_id):
    student = request.student_record
    opportunity = next((
        item for item in _open_opportunities(student)
        if item["company_drive"].company_drive_id == company_drive_id
        and item["role"].role_id == role_id
    ), None)
    if opportunity is None:
        messages.error(request, "This opportunity is closed or no longer available.")
    elif opportunity["application"]:
        messages.info(request, "You have already applied to this role.")
    elif not opportunity["eligible"]:
        messages.error(request, "You do not meet this role's current eligibility criteria.")
    else:
        try:
            with transaction.atomic():
                application = Application.objects.create(
                    student=student,
                    company_drive=opportunity["company_drive"],
                    role=opportunity["role"],
                    application_date=date.today(),
                    application_status="Applied",
                    eligibility_status="Eligible",
                )
                PlacementStatusHistory.objects.create(student_id=student.student_id, record_type="Application", record_id=application.pk, field_name="application_status", old_value="", new_value="Applied", actor=request.user)
        except IntegrityError:
            messages.info(request, "An application for this role already exists on your account.")
        else:
            messages.success(request, "Your application was submitted successfully.")
    return redirect("student_dashboard")


@student_only
def student_password_change(request):
    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        messages.success(request, "Your password has been updated.")
        return redirect("student_dashboard")
    return render(request, "placements/student_password_change.html", {
        "student": request.student_record,
        "form": form,
    })


@student_only
@require_POST
def student_logout(request):
    logout(request)
    return redirect("portal_home")


@STAFF_ONLY
def companies(request):
    queryset = Company.objects.annotate(role_count=Count("job_roles__role_id", distinct=True)).order_by("company_name")
    search = request.GET.get("q", "").strip()
    if search:
        queryset = queryset.filter(company_name__icontains=search)
    rows = [
        [company.company_name, company.industry or "—", company.headquarters or "—", company.role_count, company.company_status]
        for company in queryset
    ]
    return _records(request, title="Companies", eyebrow="Recruiting partners",
                    description="Organizations and job roles in the placement database.",
                    headers=["Company", "Industry", "Headquarters", "Roles", "Status"],
                    rows=rows, add_url="company_add", search=search)


@STAFF_ONLY
def company_add(request):
    return _record_form(request, CompanyForm, "Add company", "companies")


@STAFF_ONLY
def job_roles(request):
    queryset = JobRole.objects.select_related("company").order_by("company__company_name", "role_title")
    search = request.GET.get("q", "").strip()
    if search:
        queryset = queryset.filter(Q(role_title__icontains=search) | Q(company__company_name__icontains=search))
    rows = [
        [role.company.company_name, role.role_title, role.work_location or "—",
         role.minimum_cgpa if role.minimum_cgpa is not None else "—", role.salary_package or "—", role.role_status]
        for role in queryset
    ]
    return _records(request, title="Job roles", eyebrow="Open opportunities",
                    description="Role requirements and salary packages offered by recruiting companies.",
                    headers=["Company", "Role", "Location", "Minimum CGPA", "Package", "Status"],
                    rows=rows, add_url="job_role_add", search=search,
                    actions=[{"url": reverse("admin:placements_roleskillrequirement_changelist"), "label": "Manage role skill criteria"}])


@STAFF_ONLY
def job_role_add(request):
    return _record_form(request, JobRoleForm, "Add job role", "job_roles")


@STAFF_ONLY
def drives(request):
    queryset = PlacementDrive.objects.annotate(company_count=Count("company_drives__company_drive_id", distinct=True))
    search = request.GET.get("q", "").strip()
    if search:
        queryset = queryset.filter(Q(drive_name__icontains=search) | Q(academic_year__icontains=search))
    rows = [
        [drive.drive_name, drive.academic_year, drive.drive_type, drive.drive_start_date or "—",
         drive.company_count, drive.drive_status]
        for drive in queryset.order_by("-drive_start_date", "drive_name")
    ]
    actions = [
        {"url": reverse("company_drives"), "label": "View company drives"},
        {"url": reverse("company_drive_add"), "label": "Add company to a drive"},
    ]
    return _records(request, title="Placement drives", eyebrow="Recruitment calendar",
                    description="Recruitment events and the company drives linked to each event.",
                    headers=["Drive", "Academic year", "Type", "Start date", "Companies", "Status"],
                    rows=rows, add_url="drive_add", actions=actions, search=search)


@STAFF_ONLY
def drive_add(request):
    return _record_form(request, PlacementDriveForm, "Add placement drive", "drives")


@STAFF_ONLY
def company_drives(request):
    queryset = CompanyDrive.objects.select_related("drive", "company").order_by("-drive__drive_start_date", "company__company_name")
    search = request.GET.get("q", "").strip()
    if search:
        queryset = queryset.filter(Q(drive__drive_name__icontains=search) | Q(company__company_name__icontains=search))
    rows = [
        [item.drive.drive_name, item.company.company_name, item.registration_start or "—",
         item.registration_end or "—", item.minimum_cgpa or "—", item.maximum_backlogs, item.drive_status]
        for item in queryset
    ]
    return _records(request, title="Company drives", eyebrow="Drive registrations",
                    description="Company-specific recruitment windows and eligibility requirements.",
                    headers=["Placement drive", "Company", "Registration opens", "Registration closes",
                             "Minimum CGPA", "Maximum backlogs", "Status"],
                    rows=rows, add_url="company_drive_add", search=search)


@STAFF_ONLY
def company_drive_add(request):
    return _record_form(request, CompanyDriveForm, "Add company to a drive", "company_drives")


@STAFF_ONLY
def applications(request):
    queryset = Application.objects.select_related("student", "student__department", "company_drive__drive", "company_drive__company", "role")
    search = request.GET.get("q", "").strip()
    department_id = request.GET.get("department", "")
    academic_year = request.GET.get("academic_year", "")
    if department_id.isdigit():
        queryset = queryset.filter(student__department_id=int(department_id))
    if academic_year:
        queryset = queryset.filter(company_drive__drive__academic_year=academic_year)
    if search:
        queryset = queryset.filter(
            Q(student__student_name__icontains=search)
            | Q(student__roll_no__icontains=search)
            | Q(company_drive__company__company_name__icontains=search)
            | Q(role__role_title__icontains=search)
        )
    rows = [
        [application.application_id, application.student.student_name, application.company_drive.company.company_name,
         application.role.role_title, application.application_date, application.application_status,
         application.eligibility_status]
        for application in queryset.order_by("-application_date", "-application_id")
    ]
    actions = [
        {"url": reverse("interview_add"), "label": "Record interview"},
        {"url": reverse("selection_add"), "label": "Record selection"},
        {"url": reverse("offer_add"), "label": "Record offer"},
        {"url": reverse("interviews"), "label": "View interview rounds"},
        {"url": reverse("selections"), "label": "View selections"},
        {"url": reverse("offers"), "label": "View offers"},
    ]
    return _records(request, title="Applications", eyebrow="Recruitment pipeline",
                    description="Track applications, eligibility, interviews, selections, and offers.",
                    headers=["ID", "Student", "Company", "Role", "Applied", "Status", "Eligibility"],
                    rows=rows, add_url="application_add", actions=actions, search=search)


@STAFF_ONLY
def application_add(request):
    return _record_form(request, ApplicationForm, "Add application", "applications",
                        extra_context={"form_note": "Eligibility uses the student's recorded CGPA, backlogs, graduation year, department, and any configured role skill requirements."})


@STAFF_ONLY
def interviews(request):
    queryset = InterviewRound.objects.select_related("application__student", "application__role", "application__company_drive__company")
    rows = [
        [item.application.student.student_name, item.application.company_drive.company.company_name,
         item.application.role.role_title, item.round_number, item.round_name, item.scheduled_date or "—",
         item.score if item.score is not None else "—", item.round_status, reverse("interview_scorecard", args=[item.round_id])]
        for item in queryset.order_by("-scheduled_date", "application__student__student_name")
    ]
    return _records(request, title="Interview rounds", eyebrow="Candidate progress",
                    description="Scores and status recorded for each interview round.",
                    headers=["Student", "Company", "Role", "Round", "Stage", "Scheduled", "Score", "Status", "Scorecard"],
                    rows=rows, add_url="interview_add", actions=[{"url": reverse("status_history"), "label": "Status history"}])


@STAFF_ONLY
def interview_add(request):
    return _record_form(request, InterviewRoundForm, "Record interview round", "applications")


@STAFF_ONLY
def selections(request):
    queryset = Selection.objects.select_related("application__student", "application__company_drive__company", "application__role")
    rows = [
        [item.application.student.student_name, item.application.company_drive.company.company_name,
         item.application.role.role_title, item.selection_date, item.selection_status,
         item.final_score if item.final_score is not None else "—"]
        for item in queryset.order_by("-selection_date")
    ]
    return _records(request, title="Selections", eyebrow="Recruitment outcomes",
                    description="Selection decisions recorded for student applications.",
                    headers=["Student", "Company", "Role", "Decision date", "Decision", "Final score"],
                    rows=rows, add_url="selection_add", actions=[{"url": reverse("status_history"), "label": "Status history"}])


@STAFF_ONLY
def selection_add(request):
    return _record_form(request, SelectionForm, "Record selection decision", "applications")


@STAFF_ONLY
def offers(request):
    queryset = Offer.objects.select_related("selection__application__student", "selection__application__company_drive__company", "selection__application__role")
    rows = [
        [item.selection.application.student.student_name, item.selection.application.company_drive.company.company_name,
         item.selection.application.role.role_title, item.offer_date, item.annual_ctc or "—",
         item.offer_status, item.offer_reference_no or "—"]
        for item in queryset.order_by("-offer_date")
    ]
    return _records(request, title="Offers", eyebrow="Offer management",
                    description="Issued packages and candidate responses. Accepted offers count as placements.",
                    headers=["Student", "Company", "Role", "Offer date", "Annual CTC", "Status", "Reference"],
                    rows=rows, add_url="offer_add", actions=[{"url": reverse("admin:placements_offerresponsedeadline_changelist"), "label": "Manage response deadlines"}, {"url": reverse("status_history"), "label": "Status history"}])


@STAFF_ONLY
def offer_add(request):
    return _record_form(request, OfferForm, "Record offer", "offers")


@STAFF_ONLY
def reports(request):
    sections = []
    column_labels = {
        "student_id": "ID", "roll_no": "Roll number", "student_name": "Student",
        "department_name": "Department", "cgpa": "CGPA", "placement_status": "Placement",
        "backlogs": "Backlogs", "total_students": "Students", "placed_students": "Placed",
        "not_placed_students": "Not placed", "average_cgpa": "Average CGPA", "company_name": "Company",
        "role_title": "Role", "work_location": "Location", "salary_package": "Salary package",
        "application_id": "ID", "application_date": "Applied", "application_status": "Status",
        "eligibility_status": "Eligibility", "total_applications": "Applications",
        "selection_status": "Selection", "annual_ctc": "Annual CTC", "offer_status": "Offer",
    }
    with connection.cursor() as cursor:
        for title, sql in load_report_queries():
            if not sql.lstrip().upper().startswith("SELECT"):
                raise ValueError("Only read-only SELECT statements are supported in the report bank.")
            cursor.execute(sql)
            headers = [column_labels.get(column[0], column[0].replace("_", " ").title())
                       for column in (cursor.description or [])]
            sections.append({"title": title, "headers": headers, "rows": cursor.fetchall()})
    return render(request, "placements/reports.html", {"sections": sections})


@STAFF_ONLY
def analytics(request):
    company_rows = list(
        Company.objects.annotate(
            application_count=Count("company_drives__applications__application_id", distinct=True),
            applicant_count=Count("company_drives__applications__student_id", distinct=True),
            selected_count=Count(
                "company_drives__applications__selection__selection_id",
                filter=Q(company_drives__applications__selection__selection_status__iexact="Selected"), distinct=True,
            ),
            rejected_count=Count(
                "company_drives__applications__application_id",
                filter=Q(company_drives__applications__application_status__iexact="Rejected")
                | Q(company_drives__applications__selection__selection_status__iexact="Rejected"), distinct=True,
            ),
            placed_count=Count(
                "company_drives__applications__student_id",
                filter=Q(company_drives__applications__selection__offer__offer_status__in=["Accepted", "Joined"]),
                distinct=True,
            ),
            offer_count=Count("company_drives__applications__selection__offer__offer_id", distinct=True),
            average_ctc=Avg("company_drives__applications__selection__offer__annual_ctc"),
        ).order_by("-application_count", "company_name")
    )
    for company in company_rows:
        company.selection_rate = round(company.selected_count * 100 / company.applicant_count) if company.applicant_count else 0

    student_count = Student.objects.count()
    placed_count = Student.objects.filter(placement_status__iexact="Placed").count()
    average_cgpa = Student.objects.aggregate(value=Avg("cgpa"))["value"]
    high_performers = Student.objects.filter(cgpa__gte=8, backlogs=0).count()
    interview_average = InterviewRound.objects.aggregate(value=Avg("score"))["value"]
    total_applications = Application.objects.count()
    total_selected = Selection.objects.filter(selection_status__iexact="Selected").count()
    total_rejected = Application.objects.filter(
        Q(application_status__iexact="Rejected") | Q(selection__selection_status__iexact="Rejected")
    ).distinct().count()
    total_offers = Offer.objects.count()

    departments = list(Department.objects.annotate(
        student_count=Count("students__student_id", distinct=True),
        placed_count=Count("students__student_id", filter=Q(students__placement_status__iexact="Placed"), distinct=True),
        average_cgpa=Avg("students__cgpa"),
    ).order_by("department_name"))
    for department in departments:
        department.placement_rate = round(department.placed_count * 100 / department.student_count) if department.student_count else 0

    performance_students = list(Student.objects.select_related("department").annotate(
        application_count=Count("applications__application_id", distinct=True),
        selected_count=Count(
            "applications__selection__selection_id",
            filter=Q(applications__selection__selection_status__iexact="Selected"), distinct=True,
        ),
        average_interview_score=Avg("applications__interview_rounds__score"),
    ).order_by("-cgpa", "backlogs", "student_name"))
    with connection.cursor() as cursor:
        cursor.execute("SELECT student_id, COUNT(*) FROM student_skills GROUP BY student_id")
        skill_counts = dict(cursor.fetchall())
    for student in performance_students:
        student.skill_count = skill_counts.get(student.student_id, 0)
        student.review_signals = []
        if student.application_count == 0 and student.placement_status.casefold() != "placed":
            student.review_signals.append("No applications recorded")
        if student.cgpa < 8:
            student.review_signals.append("Below 8.0 academic reference")
        if student.backlogs:
            student.review_signals.append(f"{student.backlogs} backlog(s) recorded")
        if student.skill_count == 0:
            student.review_signals.append("No skills recorded")
        if student.average_interview_score is None:
            student.review_signals.append("No interview scores yet")
        if student.average_interview_score is not None and student.average_interview_score < 75:
            student.review_signals.append("Interview average below 75/100")

    return render(request, "placements/analytics.html", {
        "company_rows": company_rows,
        "student_count": student_count,
        "placed_count": placed_count,
        "placement_rate": round(placed_count * 100 / student_count) if student_count else 0,
        "average_cgpa": average_cgpa,
        "high_performers": high_performers,
        "interview_average": interview_average,
        "total_applications": total_applications,
        "total_selected": total_selected,
        "total_rejected": total_rejected,
        "total_offers": total_offers,
        "departments": departments,
        "performance_students": performance_students,
    })


@STAFF_ONLY
def student_performance(request, student_id):
    student = get_object_or_404(Student.objects.select_related("department"), pk=student_id)
    applications = Application.objects.filter(student=student).select_related(
        "company_drive__company", "role", "selection__offer"
    ).prefetch_related("interview_rounds").order_by("-application_date")
    application_count = applications.count()
    selected_count = Selection.objects.filter(application__student=student, selection_status__iexact="Selected").count()
    rejected_count = Application.objects.filter(student=student).filter(
        Q(application_status__iexact="Rejected") | Q(selection__selection_status__iexact="Rejected")
    ).distinct().count()
    offer_count = Offer.objects.filter(selection__application__student=student).count()
    current_opportunities = _open_opportunities(student)
    eligible_opportunity_count = sum(1 for item in current_opportunities if item["eligible"])
    interview_summary = InterviewRound.objects.filter(application__student=student).aggregate(
        average=Avg("score"), scored_rounds=Count("round_id", filter=Q(score__isnull=False)),
    )
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT sk.skill_name, ss.proficiency_level, ss.years_of_experience
               FROM student_skills AS ss INNER JOIN skills AS sk ON sk.skill_id = ss.skill_id
               WHERE ss.student_id = %s ORDER BY sk.skill_name""",
            [student.student_id],
        )
        skills = [{"name": row[0], "level": row[1], "experience": row[2]} for row in cursor.fetchall()]

    average_score = interview_summary["average"]
    performance_notes = []
    if current_opportunities:
        performance_notes.append(
            f"Currently meets the posted criteria for {eligible_opportunity_count} of {len(current_opportunities)} open roles."
        )
    else:
        performance_notes.append("No currently open roles are available for an eligibility comparison.")
    if student.cgpa >= 8 and student.backlogs == 0:
        performance_notes.append("Strong academic standing with no current backlogs.")
    elif student.backlogs:
        performance_notes.append("Clearing current backlogs is the clearest academic priority.")
    else:
        performance_notes.append("A stronger CGPA can improve this academic profile.")
    if average_score is None:
        performance_notes.append("No scored interview rounds are recorded yet.")
    elif average_score >= 75:
        performance_notes.append("Recorded interview scores show a strong average.")
    else:
        performance_notes.append("Review interview feedback and practise the skills tested in lower-scored rounds.")
    if application_count and selected_count == 0:
        performance_notes.append("Review application outcomes and interview feedback to choose the next preparation step.")
    semester_count = SemesterPerformance.objects.filter(student_id=student.student_id).count()
    if semester_count:
        performance_notes.append(f"{semester_count} semester record(s) support an academic progress trend.")
    else:
        performance_notes.append("No term-level history is recorded yet; add verified semester results to show progress over time.")
    performance_report = _student_performance_report_data(student, include_private_feedback=True)

    return render(request, "placements/student_performance.html", {
        **performance_report,
        "student": student,
        "application_count": application_count,
        "selected_count": selected_count,
        "rejected_count": rejected_count,
        "offer_count": offer_count,
        "eligible_opportunity_count": eligible_opportunity_count,
        "open_opportunity_count": len(current_opportunities),
        "average_interview_score": average_score,
        "scored_interview_rounds": interview_summary["scored_rounds"],
        "skills": skills,
        "applications": applications,
        "performance_notes": performance_notes,
        "semester_records": SemesterPerformance.objects.filter(student_id=student.student_id).order_by("academic_year", "semester"),
        "interview_category_scores": InterviewCategoryScore.objects.filter(interview_round_id__in=InterviewRound.objects.filter(application__student=student).values_list("round_id", flat=True)).order_by("interview_round_id", "category"),
        "status_history": PlacementStatusHistory.objects.filter(student_id=student.student_id).select_related("actor")[:30],
    })
