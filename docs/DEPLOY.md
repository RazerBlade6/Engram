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

## How the worker wakes

The worker isn't running between jobs. When a job is queued, a trigger on `public.jobs`
posts to the worker's `wake` endpoint, which starts `drain`: it runs jobs until none is
ready, then stops. A sweep every 15 minutes picks up retries whose backoff has passed and
jobs left behind by a worker that died. Only one `drain` runs at a time.

The wake URL and its token live in the database's Vault (`worker_wake_url`,
`worker_wake_token`). Without them, as in local development, the trigger does nothing.

## Configuration

Nothing secret is in the repository.

- **Cloud Run** reads `ENGRAM_DATABASE_URL`, `ENGRAM_SUPABASE_SECRET_KEY` and
  `ANTHROPIC_API_KEY` from Secret Manager (`engram-database-url`,
  `engram-supabase-secret-key`, `engram-anthropic-api-key`), and plain settings from its
  environment. The deploy workflow changes only the image.
- **Modal** reads everything from the secret `engram`, including `ENGRAM_WORKER_WAKE_TOKEN`.
- **Vercel** has `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` and
  `NEXT_PUBLIC_API_URL`.
- **GitHub Actions** has `SUPABASE_DB_PASSWORD` (migrations connect through the session
  pooler), `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET`. Google Cloud access needs no key: the workflow signs in through
  workload identity federation, trusted only for `main` of this repository.
- Both the API and the worker connect through Supabase's session pooler (port 5432), which
  works over IPv4 and keeps prepared statements working.

## Deploying by hand

```sh
supabase link --project-ref <ref> && supabase db push
cd backend && uv run --with modal modal deploy modal_app.py
docker build -t <region>-docker.pkg.dev/<project>/engram/api:<tag> backend   # then push
gcloud run deploy engram-api --image <that image> --region asia-northeast3
```
