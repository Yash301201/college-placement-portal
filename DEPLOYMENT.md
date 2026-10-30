# Make the portal public and deploy on GitHub pushes

`http://127.0.0.1:8000/` is only a local development address. GitHub stores the code; it does not run this Django application. To give recruiters a working link, deploy the app and database to a hosting service. This guide uses Railway because it supports Django, MySQL, and deployments triggered by pushes to a linked GitHub branch.

## Before you start

- Create a Railway account and connect it to GitHub. This project is already connected to `Yash301201/college-placement-portal`, branch `main`.
- Railway has a Free plan with limited monthly usage and paid plans. Review [current Railway pricing](https://docs.railway.com/pricing) before enabling a paid plan or usage beyond the free allowance.
- Use synthetic demo records in a public portfolio. Do not upload real student names, contact details, marks, resumes, or credentials.
- The Railway MySQL database is separate from MySQL on your PC. Import the existing schema into the Railway database, then add only data that is safe to show in a demo. Keep the database private to the Railway project; do not enable public database access for normal app traffic.

## One-time setup

1. In Railway, create a project and add a **MySQL** service.
2. Import the schema from `database/college_placement_management_db.sql` into that MySQL service. The script creates `college_placement_db`; make sure the database name used by Railway is `college_placement_db`, or adjust a copy of the import to use Railway's generated database name. If the service account cannot create databases, remove the `CREATE DATABASE` and `USE` statements from the copy and run it against the database Railway already created. The existing placement tables must exist before running Django migrations because those tables are intentionally unmanaged by Django.
3. Add a service from the GitHub repository `Yash301201/college-placement-portal` and select the `main` branch.
4. Configure the Django service commands:

   - **Build:** `python -m pip install -r requirements.txt && python manage.py collectstatic --noinput`
   - **Pre-deploy:** `python manage.py migrate`
   - **Start:** `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT`

   The start command binds to Railway's assigned port. The project settings can read Railway's `RAILWAY_PUBLIC_DOMAIN` and MySQL service variables directly.

5. In the Django service's **Variables**, add the following. If your MySQL service is named `MySQL`, the reference values shown below will work; otherwise replace `MySQL` with its exact Railway service name.

   | Variable | Value |
   | --- | --- |
   | `DJANGO_DEBUG` | `False` |
   | `DJANGO_SECRET_KEY` | A new randomly generated secret (at least 50 characters) |
   | `DB_NAME` | `${{MySQL.MYSQLDATABASE}}` |
   | `DB_USER` | `${{MySQL.MYSQLUSER}}` |
   | `DB_PASSWORD` | `${{MySQL.MYSQLPASSWORD}}` |
   | `DB_HOST` | `${{MySQL.MYSQLHOST}}` |
   | `DB_PORT` | `${{MySQL.MYSQLPORT}}` |
   | `TRUST_PROXY_SSL_HEADER` | `True` |

   The app reads the Railway-generated public domain for `ALLOWED_HOSTS` and the HTTPS CSRF origin. Do not copy `.env` to GitHub or put database passwords in source files.

   Generate the Django secret locally with:

   ```powershell
   .\.venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
   ```

6. Generate the web service's public domain from its **Settings → Networking** page. Once deployed, check the build and runtime logs. Create the first staff account from the service shell with `python manage.py createsuperuser`.

After a successful deployment, share the generated HTTPS domain and routes:

- Portal: `https://<your-generated-domain>/`
- Staff sign-in: `https://<your-generated-domain>/admin/login/`
- Student sign-in: `https://<your-generated-domain>/student/login/`

Do not share administrator credentials. Students still need a student record and portal account created by staff.

## Push-to-deploy

In the Railway service settings, enable automatic deployments from `main`. After the initial setup, push code changes with:

```powershell
git add .
git commit -m "Describe the change"
git push origin main
```

Railway will build and redeploy the connected service when it receives a new commit on the configured branch. The recruiter link stays the generated HTTPS domain; it will no longer contain `127.0.0.1`.

Before enabling resume/document uploads, attach persistent private storage and set `PRIVATE_MEDIA_ROOT` to its mount path. The default container filesystem may not preserve uploads across deployments.

References: [Railway Django deployment guide](https://docs.railway.com/guides/django), [Railway MySQL database](https://docs.railway.com/databases/mysql), [GitHub auto-deploys](https://docs.railway.com/deployments/github-autodeploys), and [pricing](https://docs.railway.com/pricing).
