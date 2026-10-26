from django.contrib import admin

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
    Skill,
    Student,
    StudentPortalAccount,
    SemesterPerformance, RoleSkillRequirement, InterviewCategoryScore, PortalReminder,
    OfferResponseDeadline, PlacementStatusHistory, StudentDocument,
)


class StudentAdmin(admin.ModelAdmin):
    list_display = ("roll_no", "student_name", "department", "cgpa", "backlogs", "placement_status")
    list_filter = ("department", "placement_status", "graduation_year")
    search_fields = ("roll_no", "student_name", "email")


class ApplicationAdmin(admin.ModelAdmin):
    def save_model(self, request, obj, form, change):
        old = None
        if change:
            old = Application.objects.filter(pk=obj.pk).values_list("application_status", flat=True).first()
        super().save_model(request, obj, form, change)
        new = obj.application_status or ""
        if old != new:
            PlacementStatusHistory.objects.create(
                student_id=obj.student_id, record_type="Application", record_id=obj.pk,
                field_name="application_status", old_value=old or "", new_value=new, actor=request.user,
            )

    list_display = ("application_id", "student", "role", "application_date", "application_status", "eligibility_status")
    list_filter = ("application_status", "eligibility_status", "application_date")
    search_fields = ("student__student_name", "role__role_title", "company_drive__company__company_name")


class JobRoleAdmin(admin.ModelAdmin):
    list_display = ("role_title", "company", "work_location", "salary_package", "role_status")
    list_filter = ("role_status", "employment_type", "company")
    search_fields = ("role_title", "company__company_name")


admin.site.register(Department)
admin.site.register(Student, StudentAdmin)
admin.site.register(Skill)
admin.site.register(Company)
admin.site.register(JobRole, JobRoleAdmin)
admin.site.register(PlacementDrive)
admin.site.register(CompanyDrive)
admin.site.register(Application, ApplicationAdmin)
admin.site.register(InterviewRound)
class SelectionAdmin(admin.ModelAdmin):
    list_display = ("selection_id", "application", "selection_date", "selection_status", "final_score")
    list_filter = ("selection_status", "selection_date")

    def save_model(self, request, obj, form, change):
        old = Selection.objects.filter(pk=obj.pk).values_list("selection_status", flat=True).first() if change else None
        super().save_model(request, obj, form, change)
        new = obj.selection_status or ""
        if old != new:
            PlacementStatusHistory.objects.create(
                student_id=obj.application.student_id, record_type="Selection", record_id=obj.pk,
                field_name="selection_status", old_value=old or "", new_value=new, actor=request.user,
            )


class OfferAdmin(admin.ModelAdmin):
    list_display = ("offer_id", "selection", "offer_date", "offer_status", "annual_ctc")
    list_filter = ("offer_status", "offer_date")

    def save_model(self, request, obj, form, change):
        old = Offer.objects.filter(pk=obj.pk).values_list("offer_status", flat=True).first() if change else None
        super().save_model(request, obj, form, change)
        new = obj.offer_status or ""
        if old != new:
            PlacementStatusHistory.objects.create(
                student_id=obj.selection.application.student_id, record_type="Offer", record_id=obj.pk,
                field_name="offer_status", old_value=old or "", new_value=new, actor=request.user,
            )


admin.site.register(Selection, SelectionAdmin)
admin.site.register(Offer, OfferAdmin)


@admin.register(StudentPortalAccount)
class StudentPortalAccountAdmin(admin.ModelAdmin):
    list_display = ("student_id", "user", "created_at")
    search_fields = ("=student_id", "user__username", "user__email")

admin.site.site_header = "College Placement Portal"
admin.site.site_title = "Placement Portal Admin"
admin.site.index_title = "Manage recruitment data"


@admin.register(SemesterPerformance)
class SemesterPerformanceAdmin(admin.ModelAdmin):
    list_display = ("student_id", "academic_year", "semester", "sgpa", "cumulative_cgpa", "backlogs")
    list_filter = ("academic_year", "semester")
    search_fields = ("skill_name",)


@admin.register(RoleSkillRequirement)
class RoleSkillRequirementAdmin(admin.ModelAdmin):
    list_display = ("role", "skill_name", "minimum_proficiency")
    list_filter = ("minimum_proficiency",)
    search_fields = ("role__role_title", "role__company__company_name", "skill_name")


@admin.register(InterviewCategoryScore)
class InterviewCategoryScoreAdmin(admin.ModelAdmin):
    list_display = ("interview_round_id", "category", "score", "visible_to_student", "updated_by", "updated_at")
    list_filter = ("category", "visible_to_student")


@admin.register(PortalReminder)
class PortalReminderAdmin(admin.ModelAdmin):
    list_display = ("student_id", "reminder_type", "title", "due_at", "created_by")
    list_filter = ("reminder_type", "due_at")
    search_fields = ("=student_id", "title")


@admin.register(OfferResponseDeadline)
class OfferResponseDeadlineAdmin(admin.ModelAdmin):
    list_display = ("offer_id", "response_deadline", "updated_by", "updated_at")


@admin.register(PlacementStatusHistory)
class PlacementStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("changed_at", "student_id", "record_type", "record_id", "field_name", "old_value", "new_value", "actor")
    list_filter = ("record_type", "field_name", "changed_at")
    search_fields = ("=student_id", "=record_id", "old_value", "new_value", "actor__username")
    readonly_fields = tuple(field.name for field in PlacementStatusHistory._meta.fields)


@admin.register(StudentDocument)
class StudentDocumentAdmin(admin.ModelAdmin):
    list_display = ("student_id", "original_name", "uploaded_at")
    search_fields = ("=student_id", "original_name")
    fields = ("student_id", "original_name", "uploaded_at")
    readonly_fields = fields
