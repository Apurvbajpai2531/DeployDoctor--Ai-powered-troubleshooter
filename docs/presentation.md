# DeployDoctor: presentation notes

Fill in the TODO items before presenting. Do not claim anything that is not built; the "Implemented vs future" lists in the README are the source of truth.

## Before you present

Do these the day before and again an hour before:

- [ ] `docker compose ps` is healthy locally, or the Elastic Beanstalk URL answers `/health` with `"database":"ok"`
- [ ] `python scripts/demo_check.py` shows no FALLBACK results and diagnoses that match each sample's real cause (run it once: each sample is a real AI call and the limit is 10 per minute)
- [ ] Groq key works and the model is still listed on the Groq models page
- [ ] Open the site in a private window so History starts empty
- [ ] Browser zoom at 110 to 125 percent; close other tabs and notifications
- [ ] Charger plugged in; phone hotspot ready as a network backup
- [ ] No `.env`, key, or AWS account number visible on screen
- [ ] If the environment is live: you know the terminate command and will run it after the event

## Backup plan

1. **Local fallback:** the same demo runs on your laptop with `docker compose up`. Keep it running in another tab.
2. **Offline example:** `/?preview=result` shows a **canned example** of a diagnosis without calling the AI. If the AI or the network fails, use it, and say plainly that it is a saved example.
3. **Recording:** keep a 60-second screen recording of the real flow on your laptop and phone.
4. If Groq is slow, say so while it runs and keep talking through the architecture. Do not refresh.

## 2-minute pitch

Every developer knows this moment: the deployment fails, and you are staring at four hundred lines of logs hoping the real error jumps out. Finding it costs time. Understanding it costs DevOps experience, and many teams, especially new ones, are shipping to the cloud faster than they can build that experience.

DeployDoctor closes that gap. You paste a failing log, pick a category such as Kubernetes or Terraform, and get back a structured incident diagnosis: the symptom, the root cause, the evidence from your own log, the fix with commands, and how to prevent it. It also gives a severity and a confidence score.

This is not a chatbot. The model has to answer in strict JSON, which we validate on the server. If it quotes a log line that is not actually in your log, we drop it. If it cannot give a valid answer after one retry, we say so honestly instead of guessing. And before your log leaves our server, common secrets like keys, tokens, and passwords are masked.

It runs as one Docker container with a PostgreSQL database, with a CI pipeline that tests it on every push, and it is configured for AWS Elastic Beanstalk, which gives us provisioning, health monitoring, and CloudWatch logs without hand-building infrastructure. TODO: the live URL is [your URL].

The API is stateless and the database is shared, so the design can grow behind a load balancer. We have been careful to separate what works today from what comes next: autoscaling, a queue for slow AI calls, caching, and real authentication.

DeployDoctor turns raw failure logs into clear fixes, and helps more teams ship with confidence.

## 5-minute demo script

| Time | Do | Say |
|---|---|---|
| 0:00 | Open the site. Point at "API online". | "This is DeployDoctor. The green dot is a live health check against the API and database." |
| 0:20 | Click the **Kubernetes CrashLoopBackOff** sample. | "A pod keeps restarting. Here is the kind of output you would get from kubectl. Notice the category selected itself." |
| 0:40 | Click **Analyze Failure**. | "While it runs: the server masks secrets first, then asks the model for JSON, then validates it." |
| 1:00 | Show the vitals panel. | "Severity with a plain-language meaning, a confidence score, the affected component." |
| 1:15 | Scroll the timeline: Symptom, Root cause, Evidence. | "Symptom, root cause, evidence. Every evidence line is checked against the log. Anything the model made up is removed." |
| 1:50 | Show Fix, click **Copy** on a command. | "Commands are suggestions. DeployDoctor never executes anything." |
| 2:10 | Show Prevention and **DevOps Insight**. | "This is the learning part: why it happened and how to avoid it." |
| 2:30 | Load the **PostgreSQL timeout** sample and analyze. | "A different domain. It should point at network reachability, not a wrong password." |
| 3:15 | Paste a log with a fake password line, for example `DATABASE_URL=postgresql://deploy:FakePass123@db:5432/app`, and analyze. | "Secrets are masked before analysis and saving. The banner tells you how many." |
| 3:45 | Show History. Open an older item. Click **Copy report**. | "History is per browser. The whole diagnosis copies as Markdown for a ticket." |
| 4:10 | Open the README architecture diagram (or a slide). | "One container, PostgreSQL, Groq. CI runs lint, tests on SQLite and PostgreSQL, and a Docker smoke test." |
| 4:35 | Close. | "What works today versus what comes next is spelled out in the README. Thank you." |

## Architecture explanation

The browser talks to one Docker container. Inside it, nginx (provided by Elastic Beanstalk) forwards to Gunicorn running FastAPI, which also serves the static frontend. On an analysis request the app validates and sanitizes the input, masks secrets, calls Groq in JSON mode, validates the answer with Pydantic, verifies evidence against the log, saves the result to PostgreSQL through SQLAlchemy, and returns it. No state is kept in the app process, so another copy of the container would behave identically.

## Why Elastic Beanstalk

- It provisions the instance, networking, health monitoring, and log streaming from a Docker image, so a small team can deploy a real service quickly.
- The Docker platform runs the same image we test in CI and locally, which removes "works on my machine".
- It can grow into a load-balanced, auto-scaled environment by configuration changes rather than a rewrite.
- Trade-off, said honestly: you get less control than with ECS or Kubernetes, and a single-instance environment has a short interruption during deploys. For this project the speed of getting to a working deployment mattered more.

## How it scales

**Today:** the API is stateless, state is in PostgreSQL, configuration is environment-only, and each instance runs several workers. The environment we deploy is a single instance.

**Next, in order of impact:**
1. A load balancer and Auto Scaling for the web tier (the app already supports running behind one).
2. Move AI calls to a queue and worker, because the slowest part is the model call, not the web tier.
3. Cache repeated analyses (hash of the masked log plus category) and share rate limits through Redis.
4. A Multi-AZ database that outlives the environment, and read-only history queries if needed.

**Where it would break first:** the Groq rate limits and latency, then web workers blocked on those calls. That is why the queue is the second step.

## Security explanation

- Secrets: environment variables only; `.env` is excluded from Git, the image, and the deploy bundle.
- Input: sanitized, size-limited at three levels (text, upload, request body), upload type and content checked.
- Privacy: common secret formats are masked before the log reaches the AI provider or the database. This is best-effort, and the UI says so.
- Web: strict headers and a CSP with no inline script or style; the UI inserts all dynamic text as text, never as HTML.
- Data: ORM queries only; each session sees only its own analyses.
- Abuse: rate limits; generic error messages that never echo input.
- Safety: commands are only ever displayed; nothing is executed.
- Honest gaps: session ID is not authentication, rate limits are per worker, default Elastic Beanstalk URL is HTTP, and the CLI IAM user is broad.

## AI explanation

- The system prompt sets the role (SRE and DevOps engineer), the severity scale, a confidence scale, and the output schema.
- The category adds specific hints, but the model is told it is only a hint and to overrule it if the log says otherwise.
- The log is delimited and declared untrusted data, so instructions inside a log are ignored.
- JSON mode, low temperature, and Pydantic validation; one corrective retry that tells the model what was wrong; then a flagged fallback.
- Evidence verification in code removes quoted lines that are not in the log, and caps confidence if none remain.
- The model name is an environment variable. The model we first chose was retired, and switching was a one-line change.

## DevOps explanation

- Docker: multi-stage build, non-root user, health check, migrations applied on start with retries, `exec` so the app receives stop signals.
- Docker Compose: the app waits for a healthy database.
- CI: lint and secret scan; tests on SQLite and on PostgreSQL; migrations tested up, down, and up; a Docker smoke test against a real database.
- Observability: structured JSON logs with request IDs and timings, a `/health` endpoint that checks the database, CloudWatch log streaming on Elastic Beanstalk.
- Delivery: manual `eb deploy` today; continuous delivery with GitHub OIDC is a future step.
- Dependabot keeps pinned dependencies and actions current.

## Future improvements

Autoscaling behind a load balancer; queue-based analysis; caching and shared rate limiting; real authentication; Multi-AZ RDS separate from the environment; TLS with certificate verification to the database; Secrets Manager; least-privilege IAM; continuous deployment; browser end-to-end tests; image vulnerability scanning; integrations (GitHub Actions or Kubernetes event ingestion) so logs arrive without pasting.

## Possible judge questions

**Why not just paste the log into a general chatbot?**
You can, and it can work. DeployDoctor gives a fixed structure you can compare and store, checks evidence against your actual log, masks secrets first, and keeps history. It is a workflow around the model, not just the model.

**How do you stop the AI from making things up?**
We cannot stop it completely. We reduce it: the prompt forbids invented evidence, the output is schema-validated, and evidence lines that are not in the log are removed in code. Low evidence lowers the confidence score. We also tell users that AI can be wrong and that commands are suggestions.

**How accurate is it?**
We have not run a benchmark, so we do not quote a percentage. We test it against seven realistic logs with known root causes, which anyone can reproduce with `scripts/demo_check.py`.

**What happens to my logs and secrets?**
Logs are sent to an AI provider. Before that, common secret formats are masked on our server, and the masked version is what we store. Masking is best-effort, so users should still avoid pasting credentials.

**Could the AI run something dangerous?**
No. The server never executes commands. They are displayed for a human to review.

**What if Groq is down or slow?**
The call has a timeout and returns a clear 502, 503, or 504 with a safe message. Rate-limit responses ask the user to retry. We do not retry timeouts automatically. A queue and a fallback provider are future work.

**How does it scale?**
The API is stateless with state in PostgreSQL, so more instances can run behind a load balancer. Today we deploy one instance; autoscaling is configuration work we have not done. The first real bottleneck is the AI provider, so a queue comes next.

**Why a single container for frontend and backend?**
One deployable unit fits Elastic Beanstalk's Docker platform, avoids CORS, and keeps the demo simple. A CDN for the static files is a possible later step.

**Is it secure to use a session ID without login?**
It separates browsers but is not authentication. Anyone with the ID can read that history. Real accounts are on the future list.

**Why PostgreSQL with JSON columns?**
The lists in a diagnosis (evidence, fix steps, commands) are display-only, so JSON columns are simpler than child tables, while PostgreSQL gives us constraints, migrations, and RDS.

**What does it cost to run?**
A single small instance plus a small RDS database, billed hourly, so we create it for the event and terminate it afterwards. We have not quoted a figure; use the AWS pricing calculator for your region.

**Why not ECS, Lambda, or Kubernetes?**
Elastic Beanstalk was the hackathon's platform, and it gets a Docker app running with health checks and logs quickly. ECS or Kubernetes give more control when you need it.

**How is it tested?**
A pytest suite that never calls the real AI, run in CI on SQLite and PostgreSQL, plus migration and Docker smoke tests. The frontend has static checks but no browser tests yet.

**What would you build next?**
Queue-based analysis, caching, real accounts, and integrations that pull logs directly from GitHub Actions or Kubernetes.

## Things not to claim

- Any accuracy percentage or user count
- That it autoscales, uses HTTPS, or encrypts the database connection with certificate verification, unless you have since built and verified it
- That secrets are never exposed (say "common formats are masked")
- That it is production-ready; say "hackathon build with a clear path to production"
