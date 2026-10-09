# DeployDoctor

> Find the failure. Understand the cause. Fix the deployment.

![CI](https://github.com/Apurvbajpai2531/DeployDoctor--Ai-powered-troubleshooter/actions/workflows/ci.yml/badge.svg)

An AI-powered DevOps troubleshooting tool. Paste a failing deployment or application log and get a **structured incident diagnosis** instead of a wall of text: symptom, root cause, evidence from your log, fix, and prevention.

Built for the **Build on Elastic Beanstalk** hackathon (theme: *How DevOps Evolves India*).

- **Live demo:** TODO (add the Elastic Beanstalk URL after deploying)
- **Deployment status:** TODO (the Elastic Beanstalk configuration is in this repo; update this line once the environment is live)

## Problem

When a deployment fails, developers scroll through hundreds of log lines looking for the one that matters. Finding it takes time, and knowing what it means takes DevOps experience that many teams, especially newer ones, do not have in-house yet. Generic chatbots help, but they answer in free text, can invent evidence, and see whatever secrets you pasted.

## Solution

DeployDoctor turns a raw log into a diagnosis with a fixed shape:

```
Symptom -> Root cause -> Evidence -> Fix -> Prevention
```

plus a severity, a confidence score, the affected component, and a short DevOps insight. The model must answer in strict JSON that is validated server-side, and any "evidence" it quotes that is not actually in your log is dropped.

## Features

**Diagnosis**
- Paste a log or upload a `.log`/`.txt`/`.out` file (drag and drop works too)
- Choose a failure category (Docker, Kubernetes, CI/CD, Linux, AWS, Terraform, Application, Database, Networking, or Unknown); the prompt reasons specifically about it
- Severity (LOW to CRITICAL), confidence, affected component, evidence, ordered fix steps, suggested commands, prevention advice, and a DevOps insight
- Copy the whole diagnosis as Markdown for a ticket or postmortem
- Seven built-in sample logs for a quick demo

**Reliability of the AI output**
- JSON mode plus Pydantic validation of the model's answer
- One corrective retry, then an honest, clearly flagged low-confidence fallback
- Evidence verification: quoted lines that do not appear in the log are removed (and confidence is capped if none remain)
- The prompt tells the model to state uncertainty and never invent evidence

**Product**
- Per-browser analysis history (reopen, delete, paginate)
- Live API status in the header
- Responsive dashboard with loading, empty, and error states

**Engineering**
- FastAPI, PostgreSQL with Alembic migrations, Docker, Docker Compose, GitHub Actions CI
- Structured JSON logging with request IDs and timings, a `/health` endpoint that checks the database
- Elastic Beanstalk configuration (Docker platform, CloudWatch log streaming)

## How it works

```mermaid
sequenceDiagram
  participant B as Browser
  participant A as FastAPI
  participant G as Groq
  participant D as PostgreSQL
  B->>A: POST /api/analyze (log, category, X-Session-ID)
  A->>A: validate, sanitize, mask secrets
  A->>G: prompt + log (JSON mode)
  G-->>A: JSON diagnosis
  A->>A: validate with Pydantic, retry once, verify evidence
  A->>D: save analysis
  A-->>B: structured diagnosis
```

## Architecture

```mermaid
flowchart LR
  U[Browser] -->|HTTP| NGX[Elastic Beanstalk nginx]
  subgraph EB[Elastic Beanstalk single instance]
    NGX --> APP[Docker container: Gunicorn + FastAPI + static frontend]
  end
  APP -->|SQLAlchemy| RDS[(RDS PostgreSQL)]
  APP -->|HTTPS, key from environment| GROQ[Groq API]
  EB -.->|log streaming| CW[CloudWatch Logs]
```

One container serves both the API and the static frontend, so there is a single deployable unit and no CORS in normal use. The API is stateless: all state is in PostgreSQL.

## Tech stack

| Area | Choice |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic, SQLAlchemy, Alembic |
| Database | PostgreSQL 16 (Docker locally, RDS on AWS) |
| AI | Groq API (model set by `GROQ_MODEL`, default `openai/gpt-oss-120b`) |
| Frontend | Plain HTML, CSS, JavaScript (no framework, no build step) |
| Server | Gunicorn with Uvicorn workers |
| Containers | Docker (multi-stage, non-root), Docker Compose |
| CI | GitHub Actions |
| Cloud | AWS Elastic Beanstalk (Docker on Amazon Linux 2023), RDS, CloudWatch |
| Tests | pytest |

## Project structure

```
deploydoctor/
├── backend/
│   ├── app/
│   │   ├── main.py, config.py, database.py, logging_config.py
│   │   ├── models/analysis.py
│   │   ├── schemas/        analysis.py, ai_output.py, health.py
│   │   ├── routes/         analysis.py, upload.py, health.py
│   │   ├── services/       ai_service.py, analyzer.py, analysis_service.py, prompts.py
│   │   └── utils/          ai_output.py, ratelimit.py, sanitize.py, session.py
│   ├── alembic/            database migrations
│   ├── tests/
│   ├── requirements.txt, requirements-dev.txt
├── frontend/               index.html, style.css, app.js, samples.js
├── scripts/demo_check.py   runs every sample log against a running instance
├── .platform/nginx/conf.d/ nginx override for Elastic Beanstalk (upload size)
├── .ebextensions/          Elastic Beanstalk settings (non-secret)
├── .github/workflows/ci.yml
├── Dockerfile, docker-entrypoint.sh, docker-compose.yml
├── .env.example, .ebignore, .dockerignore
└── docs/presentation.md
```

## Local setup

### Option 1: Docker Compose (app + PostgreSQL)

```bash
git clone https://github.com/Apurvbajpai2531/DeployDoctor--Ai-powered-troubleshooter.git deploydoctor
cd deploydoctor
cp .env.example .env
# edit .env and set GROQ_API_KEY (create a key at https://console.groq.com)
docker compose up --build
```

Open http://localhost:8000. The app waits for the database to be healthy and applies migrations on start.

### Option 2: run the backend directly

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements-dev.txt
cp .env.example .env            # set GROQ_API_KEY
docker compose up -d db         # PostgreSQL on localhost:5433
cd backend
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### Try it without typing a log

```bash
# with the app running and a real GROQ_API_KEY set
python scripts/demo_check.py
```

## Environment variables

Copy `.env.example` to `.env`. Never commit `.env`.

| Variable | Default | Purpose |
|---|---|---|
| `GROQ_API_KEY` | (empty) | Groq API key. Required for analysis. |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | Model name. Check the Groq model list, as models get retired. |
| `AI_TIMEOUT_SECONDS` | `30` | Per-request timeout for the AI call |
| `DATABASE_URL` | (empty) | PostgreSQL URL for local runs |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `deploy` / `deploy` / `deploydoctor` | Used by Docker Compose |
| `ENVIRONMENT` | `development` | `production` switches logs to JSON |
| `LOG_LEVEL` | `INFO` | Log level |
| `MAX_LOG_CHARS` | `50000` | Maximum characters of log accepted |
| `MAX_UPLOAD_BYTES` | `1048576` | Maximum upload size |
| `MAX_REQUEST_BYTES` | `2097152` | Maximum request body size |
| `RATE_LIMIT` | `10/minute` | Limit on `/api/analyze` per client, per worker |
| `UPLOAD_RATE_LIMIT` | `30/minute` | Limit on `/api/upload-log` |
| `CORS_ORIGINS` | `http://localhost:8000` | Allowed origins (no wildcard) |
| `TRUSTED_PROXY_HOPS` | `0` | Reverse proxies in front of the app (`1` on a single Elastic Beanstalk instance, `2` behind a load balancer) |
| `WEB_CONCURRENCY` | `2` | Gunicorn workers |
| `APP_PORT` | `8000` | Host port in Docker Compose |
| `RDS_HOSTNAME`, `RDS_PORT`, `RDS_DB_NAME`, `RDS_USERNAME`, `RDS_PASSWORD` | injected | Set by Elastic Beanstalk when RDS is attached; the app builds its database URL from them |

## API

Interactive docs: `/docs` (Swagger UI) and `/openapi.json`.

Analysis endpoints need an `X-Session-ID` header (16 to 64 letters, digits, or hyphens). The frontend generates one per browser. It separates users' histories; it is **not** authentication.

| Method | Path | Description |
|---|---|---|
| GET | `/health` | App and database status (503 if the database is down) |
| POST | `/api/analyze` | Analyze a log. Returns 201 with the diagnosis. |
| GET | `/api/analyses` | List this session's analyses (`limit`, `offset`) |
| GET | `/api/analyses/{id}` | One full analysis |
| DELETE | `/api/analyses/{id}` | Delete an analysis (204) |
| POST | `/api/upload-log` | Validate a log file and return its text |

```bash
curl -s -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -H "X-Session-ID: demo-session-0000-0001" \
  -d '{"category":"Kubernetes","log_text":"KeyError: DATABASE_URL\nBack-off restarting failed container api"}'
```

Errors: 400 (bad session header), 413 (too large), 422 (invalid input), 429 (rate limited), 502/503/504 (AI service failure, with a generic message).

## Testing

```bash
cd backend
python -m pytest
```

The suite never calls the real Groq API: the AI client is replaced by a fake, and a fixture fails any test that tries to create a real one. By default it runs on in-memory SQLite. To run it against PostgreSQL:

```bash
docker exec deploydoctor-db psql -U deploy -d deploydoctor -c "CREATE DATABASE deploydoctor_test;"
TEST_DATABASE_URL=postgresql://deploy:deploy@localhost:5433/deploydoctor_test python -m pytest
```

Coverage areas: health, input validation, large logs, AI parsing, retry and fallback, evidence verification, secret redaction, upload checks, security headers, rate limiting, session isolation, and save/get/delete. The frontend is covered by static checks (element IDs, categories, CSP compatibility), not by browser tests.

## CI/CD

`.github/workflows/ci.yml` runs on every push and pull request:

1. **Lint and secret scan:** ruff, plus a check that no `.env` or key-shaped value is committed
2. **Tests (SQLite)**
3. **Tests and migrations (PostgreSQL):** a Postgres service container; migrations are run up, down, and up again
4. **Docker build and smoke test:** builds the image, starts it next to a real PostgreSQL, and checks `/health`

Continuous *delivery* is not set up: deployment is a manual `eb deploy`.

## Deploying to AWS Elastic Beanstalk

The repo is configured for the **Docker platform on Amazon Linux 2023**. Elastic Beanstalk builds the image from the `Dockerfile`; `docker-compose.yml` is deliberately excluded from the bundle (`.ebignore`, `.gitattributes`), because Elastic Beanstalk would otherwise treat the project as a Compose deployment.

**Prerequisites:** an AWS account (MFA on root, a dedicated IAM user for the CLI), AWS CLI v2, EB CLI (`uv tool install --python 3.12 awsebcli`), and two IAM roles: `aws-elasticbeanstalk-service-role` (policies `AWSElasticBeanstalkEnhancedHealth`, `AWSElasticBeanstalkManagedUpdatesCustomerRolePolicy`) and `aws-elasticbeanstalk-ec2-role` with an instance profile of the same name (policy `AWSElasticBeanstalkWebTier`).

```bash
export AWS_PROFILE=deploydoctor AWS_DEFAULT_REGION=ap-south-1
eb init deploydoctor --platform docker --region ap-south-1 --profile deploydoctor

SUFFIX=your-unique-suffix          # lowercase letters and digits
GROQ_KEY=$(grep -E '^GROQ_API_KEY=' .env | cut -d= -f2-)

eb create deploydoctor-prod \
  --single \
  --cname deploydoctor-$SUFFIX \
  --instance-types t3.small \
  --service-role aws-elasticbeanstalk-service-role \
  --instance_profile aws-elasticbeanstalk-ec2-role \
  --database --database.engine postgres --database.instance db.t3.micro --database.size 5 \
  --envvars "GROQ_API_KEY=$GROQ_KEY,CORS_ORIGINS=http://deploydoctor-$SUFFIX.ap-south-1.elasticbeanstalk.com" \
  --timeout 40
unset GROQ_KEY
```

`eb create` asks for the database master username and password. Non-secret settings (log streaming to CloudWatch with 7-day retention, `TRUSTED_PROXY_HOPS=1`, limits) live in `.ebextensions/01-environment.config`.

```bash
eb status && eb health            # environment state
eb logs --all                     # download logs (migrations, gunicorn, app JSON logs)
eb deploy deploydoctor-prod --label v0-1-1    # ship a new commit
```

The container applies Alembic migrations on start, so a fresh RDS database gets its tables automatically.

**Cost and cleanup.** The environment bills hourly (EC2, a public IPv4 address, RDS) until you terminate it:

```bash
eb terminate deploydoctor-prod    # type the environment name to confirm
```

Afterwards check for leftovers (RDS instances and snapshots, CloudWatch log groups, the `elasticbeanstalk-*` S3 bucket) and delete the CLI user's access keys.

## Security

**Implemented**
- Secrets are never hardcoded; configuration comes from environment variables, and `.env` is git-ignored and excluded from the image and the deploy bundle
- Logs are sanitized (control characters, ANSI codes, NUL bytes) and common secret formats are masked **before** the log reaches the LLM or the database
- Size limits on log text, uploads, and request bodies; upload type and content checks
- Rate limiting on analysis and upload endpoints
- ORM queries only (no string-built SQL); analyses are scoped to the session, and another session's ID returns 404
- Strict security headers and a Content-Security-Policy with no inline scripts or styles; the UI never builds HTML from strings
- Validation errors never echo the submitted input; unexpected errors return a generic message with a request ID
- Commands in a diagnosis are suggestions only; the server never executes anything
- Container runs as a non-root user

**Limitations (stated honestly)**
- Secret masking is best-effort and cannot catch every secret
- The session ID separates browsers but is not authentication; anyone holding the ID can read that history
- Rate limits are per worker and not shared between instances
- A default Elastic Beanstalk URL is HTTP; HTTPS needs a domain and certificate
- Logs are sent to a third-party AI provider
- The deployment IAM user is broad (administrator) for hackathon speed, and secrets are Elastic Beanstalk environment properties rather than Secrets Manager entries

## Scalability

**Implemented now**
- Stateless API (no server-side sessions); all state in PostgreSQL
- One immutable container image, configured entirely through environment variables
- Multiple Gunicorn workers per instance; connection pooling with `pool_pre_ping`
- Health endpoint that checks the database, structured JSON logs, CloudWatch log streaming
- Elastic Beanstalk environment definition (currently a single instance)

**Future improvements (not implemented)**
- Load balancer plus Auto Scaling (the app is designed to run behind one; set `TRUSTED_PROXY_HOPS=2`)
- Asynchronous analysis through a queue (for example SQS and a worker) so slow AI calls do not hold web workers
- Caching of repeated analyses, and a shared rate-limit store such as Redis
- Real authentication and per-user history
- Multi-AZ database, a database separate from the environment lifecycle, TLS with certificate verification to RDS, a least-privilege database user
- Secrets in AWS Secrets Manager or SSM Parameter Store, least-privilege IAM, continuous deployment with GitHub OIDC
- Migrations as a separate release step (today they run at container start, which is fine for one instance)

## Screenshots

- TODO: dashboard (`docs/screenshots/dashboard.png`)
- TODO: diagnosis with vitals and timeline (`docs/screenshots/diagnosis.png`)
- TODO: history panel (`docs/screenshots/history.png`)

## Hackathon notes

**Theme: How DevOps Evolves India.** Teams across India are shipping to the cloud faster than they can grow senior DevOps experience. DeployDoctor shortens the gap between "the deployment failed" and "I know why and what to change" by turning logs into a structured, verifiable diagnosis. The diagnosis also works as a learning aid, because it explains the cause and the prevention in plain language.

**Differentiator.** It is not a chatbot. The output is a fixed incident structure, validated in code, with evidence checked against your actual log and secrets masked before anything leaves the server.

**Why Elastic Beanstalk.** It provisions the instance, networking, health monitoring, and log streaming from a Docker image, which let a small team ship a real deployment without hand-building infrastructure.

More material for presenting is in [`docs/presentation.md`](docs/presentation.md).

## License

MIT. See [LICENSE](LICENSE).
