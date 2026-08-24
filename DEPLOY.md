# Deploying the ACTX Screening Platform to Render

This turns the tool into a real website your whole team can use from any
device — no install, just a URL and a login.

## 1. Get your OpenSanctions API key ready
Sign up at opensanctions.org/api if you haven't already. You'll paste this
key into Render as a secret in step 4 — never into the code itself.

## 2. Put this folder in a GitHub repository
Render deploys from GitHub. Create a new **private** repository (this
contains AML/compliance logic — keep it private) and push everything in
this folder to it.

```
git init
git add .
git commit -m "ACTX screening platform"
git branch -M main
git remote add origin https://github.com/YOUR-ORG/actx-screening.git
git push -u origin main
```

## 3. Create the Render services
Go to render.com, sign in, and click **New > Blueprint**. Point it at your
GitHub repo — Render will read `render.yaml` in this folder and set up
both the web service and the database automatically.

If you'd rather do it by hand instead of the Blueprint:
- **New > PostgreSQL** — name it `actx-screening-db`, note the connection string.
- **New > Web Service** — connect your repo.
  - Build command: `pip install -r requirements.txt`
  - Start command: `gunicorn app:app --timeout 120`

## 4. Set environment variables
On the web service's **Environment** tab, add:

| Key | Value |
|---|---|
| `OPENSANCTIONS_API_KEY` | your real API key |
| `SECRET_KEY` | any long random string (Render can generate one) |
| `DATABASE_URL` | auto-filled if you used the Blueprint / linked the Postgres DB |
| `ADMIN_USERNAME` | e.g. `admin` |
| `ADMIN_PASSWORD` | a strong password \u2014 this logs in as the first admin account |

## 5. Deploy
Render builds and starts the app automatically. Once it's live, visit the
URL it gives you (something like `https://actx-screening.onrender.com`)
and log in with the admin username/password you set above.

## 6. First things to do after logging in
1. Go to **Settings** and confirm the UAE Local Terrorist List shows 171
   active entries (it ships bundled with the app).
2. Also in **Settings**, upload the UN Consolidated List: get the XML
   export from scsanctions.un.org/consolidated/ and upload it there \u2014
   this one isn't bundled since the UN doesn't publish it at a fixed URL,
   so it needs a one-time (then periodic) manual upload.
3. Add accounts for your colleagues under **Settings > Team access**.
4. Change the admin password to something only you know, once other
   admin accounts exist.

## Ongoing maintenance
- **UAE Local Terrorist List updates**: when the UAE Cabinet issues a new
  resolution, get an updated CSV in the same column format and upload it
  via **Settings** \u2014 it replaces the active list for everyone immediately.
- **UN Consolidated List updates**: the UN updates this list frequently.
  Re-download the XML from scsanctions.un.org/consolidated/ periodically
  (monthly is a reasonable cadence) and re-upload via **Settings**.
- **Costs**: Render's Starter plan (web service + Postgres) is a low
  monthly cost, predictable regardless of usage. OpenSanctions charges
  per successful screening query separately \u2014 check your plan there.
- **Backups**: Render's Postgres includes automatic daily backups on paid
  plans \u2014 worth confirming retention meets your compliance needs.

## Security notes
- Passwords are hashed (never stored in plain text).
- The OpenSanctions API key lives only in Render's environment variables
  \u2014 it's never sent to or visible from the browser.
- Use strong, unique passwords for every account; there's no password
  complexity enforcement built in yet (see "possible next steps" in the
  handover notes).
- This app has no email/password-reset flow yet \u2014 an admin resets a
  forgotten password by deleting and recreating the account, or you can
  add proper password-reset if that becomes a problem.
