import gzip
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create a compressed, transaction-consistent MySQL backup using mysqldump."

    def add_arguments(self, parser):
        parser.add_argument("--output-dir", default=os.getenv("BACKUP_DIR", str(settings.BASE_DIR / "backups")))

    def handle(self, *args, **options):
        database = settings.DATABASES["default"]
        executable = shutil.which("mysqldump")
        if not executable:
            raise CommandError("mysqldump was not found on PATH. Install the MySQL client tools first.")
        output_dir = Path(options["output_dir"]).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        destination = output_dir / f"{database['NAME']}-{stamp}.sql.gz"
        environment = os.environ.copy()
        if database.get("PASSWORD"):
            # Keep the password out of process arguments; mysqldump reads MYSQL_PWD.
            environment["MYSQL_PWD"] = database["PASSWORD"]
        command = [
            executable, "--single-transaction", "--routines", "--triggers", "--no-tablespaces",
            "--host", database["HOST"], "--port", str(database["PORT"]),
            "--user", database["USER"], database["NAME"],
        ]
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment)
            with gzip.open(destination, "wb") as backup_file:
                shutil.copyfileobj(process.stdout, backup_file)
            stderr = process.stderr.read().decode("utf-8", errors="replace")
            code = process.wait()
        except OSError as error:
            destination.unlink(missing_ok=True)
            raise CommandError(f"Could not run mysqldump: {error}") from error
        if code:
            destination.unlink(missing_ok=True)
            raise CommandError(f"mysqldump failed with exit code {code}: {stderr[-1200:]}")
        self.stdout.write(self.style.SUCCESS(f"Database backup created: {destination}"))
