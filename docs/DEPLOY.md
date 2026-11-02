# Deployment

Production is at https://engramstudy.app and runs in Seoul, next to the database. Everything
scales to zero (D35).

The domain's DNS is on Cloudflare with the proxy off, so Vercel issues the certificate. `www`
and the project's vercel.app address redirect to it, and it is the only origin the API allows.

| Part     | Where                                  | Deployed by                                   |
| -------- | -------------------------------------- | --------------------------------------------- |
| Web      | Vercel, project `engram`               | Vercel's GitHub integration, on push to `main` only (`web/vercel.json`) |
| API      | Cloud Run `engram-api`, asia-northeast3 | `.github/workflows/deploy.yml`                |
| Worker   | Modal app `engram-worker`              | `.github/workflows/deploy.yml`                |
| Database | Supabase, ap-northeast-2               | `.github/workflows/deploy.yml` (`supabase db push`) |

`main` only fast-forwards to a `dev` commit that CI passed, so the deploy workflow doesn't
test again. It applies new migrations first, then deploys the API and worker.

Both CI and deploys run only for the parts of the repository a push changed. A web-only
change runs the web checks and a Vercel build, and nothing else; documentation runs nothing.
Vercel skips its build when nothing under `web/` changed (`ignoreCommand` in
`web/vercel.json`). Running the deploy workflow by hand deploys everything.

## How the worker wakes

The worker isn't running between jobs. When a job is queued, a trigger on `public.jobs`
posts to the worker's `wake` endpoint, which starts `drain`: it runs jobs until none is
ready, then stops. A sweep every 15 minutes picks up retries whose backoff has passed and
jobs left behind by a worker that died. Modal can preempt a container mid-job, so the
worker renews a running job's lock every minute, and a lock five minutes old marks the job
as abandoned: a preempted job runs again within about 20 minutes. Removing a material
marks its jobs cancelled, and a running one stops at its next renewal. Only one `drain`
runs at a time.

The wake URL and its token live in the database's Vault (`worker_wake_url`,
`worker_wake_token`). Without them, as in local development, the trigger does nothing.

## Alerts

The sweep also emails the operator (D99, `backend/src/engram/alerts.py`) about:

- a job that failed for good, with its error;
- a job still waiting to start an hour after it was due: the worker isn't being woken, or a
  long job is holding it up;
- a request the API failed with a server error, including an Ask answer cut off midway. The
  API records the route, the exception's type and the line it came from in `api_errors`, never
  the message; the traceback is in Cloud Run's logs;
- estimated inference spend over $5 in a UTC day or $30 in a UTC month, from the tokens in
  `llm_usage` at list prices. The Anthropic console has the actual bill.

Everything new goes out in one email, and each alert is sent once (`alerts_sent`). An email
that fails to send is tried again at the next sweep. Without `ENGRAM_ALERT_EMAIL` and
`ENGRAM_SMTP_HOST` the alerts are only logged. To run a check by hand:
`cd backend && uv run python -m engram.alerts`.

An API so broken that requests never reach it records nothing, so Google Cloud Monitoring
also checks it: the uptime check `engram-api-health` asks the API's `/health` every 15
minutes from Asia, the US and Europe, and the alert policy "Engram API is down" emails the
operator when two of the three fail. Both were set up by hand, like the Cloud Run service.
What nothing sees is a sweep that isn't running at all (a failed Modal deploy): that shows
as no alerts.

## Configuration

Nothing secret is in the repository.

- **Cloud Run** reads `ENGRAM_DATABASE_URL`, `ENGRAM_SUPABASE_SECRET_KEY` and
  `ANTHROPIC_API_KEY` from Secret Manager (`engram-database-url`,
  `engram-supabase-secret-key`, `engram-anthropic-api-key`), and plain settings from its
  environment. The deploy workflow changes only the image.
- **Modal** reads everything from the secret `engram`, including `ENGRAM_WORKER_WAKE_TOKEN`
  and the alert email settings: `ENGRAM_ALERT_EMAIL` (where alerts go), `ENGRAM_SMTP_HOST`,
  `ENGRAM_SMTP_PORT` (587 with STARTTLS, or 465), `ENGRAM_SMTP_USERNAME`,
  `ENGRAM_SMTP_PASSWORD` and `ENGRAM_SMTP_FROM` (the sender, if not the alert address). The
  same SMTP account as Supabase Auth's emails works. The spend levels can be changed with
  `ENGRAM_ALERT_DAILY_SPEND_USD` and `ENGRAM_ALERT_MONTHLY_SPEND_USD`.
- **Vercel** has `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` and
  `NEXT_PUBLIC_API_URL`.
- **GitHub Actions** has `SUPABASE_DB_PASSWORD` (migrations connect through the session
  pooler), `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET`. Google Cloud access needs no key: the workflow signs in through
  workload identity federation, trusted only for `main` of this repository.
- Both the API and the worker connect through Supabase's session pooler (port 5432), which
  works over IPv4 and keeps prepared statements working.
- **Supabase Auth** settings are set in the dashboard, not by deploys (`supabase/config.toml`
  is local only). Its redirect URLs must include `https://engramstudy.app/auth/set-password`
  (invites) and `https://engramstudy.app/auth/reset-password` (password resets), and its
  emails go out through custom SMTP.

## Deploying by hand

```sh
supabase link --project-ref <ref> && supabase db push
cd backend && uv run --with modal modal deploy modal_app.py
docker build -t <region>-docker.pkg.dev/<project>/engram/api:<tag> backend   # then push
gcloud run deploy engram-api --image <that image> --region asia-northeast3
```
