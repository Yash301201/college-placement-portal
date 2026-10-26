from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("placements", "0002_application_company_companydrive_department_and_more")]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RemoveConstraint(
                    model_name="roleskillrequirement",
                    name="uniq_role_skill_requirement",
                ),
                migrations.RemoveField(
                    model_name="roleskillrequirement",
                    name="role_id",
                ),
                migrations.AddField(
                    model_name="roleskillrequirement",
                    name="role",
                    field=models.ForeignKey(
                        db_column="role_id",
                        db_constraint=False,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="skill_requirements",
                        to="placements.jobrole",
                    ),
                ),
                migrations.AddConstraint(
                    model_name="roleskillrequirement",
                    constraint=models.UniqueConstraint(
                        fields=("role", "skill_name"),
                        name="uniq_role_skill_requirement",
                    ),
                ),
            ],
        ),
    ]
