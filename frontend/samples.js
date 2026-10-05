"use strict";

/* Demo logs for "Try a sample log". All values are fictional. */
window.SAMPLE_LOGS = Object.freeze([
  {
    id: "docker",
    label: "Docker build",
    category: "Docker",
    log: String.raw`[+] Building 14.2s (8/10)                                          docker:default
 => [internal] load build definition from Dockerfile                          0.0s
 => [internal] load metadata for docker.io/library/python:3.14-slim           1.1s
 => [2/6] WORKDIR /app                                                        0.1s
 => [3/6] COPY backend/requirements.txt .                                     0.1s
 => ERROR [4/6] RUN pip install --no-cache-dir -r requirements.txt           12.6s
------
 > [4/6] RUN pip install --no-cache-dir -r requirements.txt:
1.904 Collecting pydantic-core==2.27.2 (from pydantic==2.10.4->-r requirements.txt (line 4))
2.351   Downloading pydantic_core-2.27.2.tar.gz (413 kB)
2.912   Installing build dependencies: started
11.84       error: the configured Python interpreter version (3.14) is newer than PyO3's maximum supported version (3.13)
12.31   ERROR: Failed building wheel for pydantic-core
12.31 Failed to build pydantic-core
12.31 ERROR: Failed to build installable wheels for some pyproject.toml based projects
------
Dockerfile:6
--------------------
   4 |     WORKDIR /app
   5 |     COPY backend/requirements.txt .
   6 | >>> RUN pip install --no-cache-dir -r requirements.txt
   7 |     COPY backend/ .
--------------------
ERROR: failed to solve: process "/bin/sh -c pip install --no-cache-dir -r requirements.txt" did not complete successfully: exit code: 1`,
  },
  {
    id: "kubernetes",
    label: "Kubernetes CrashLoopBackOff",
    category: "Kubernetes",
    log: String.raw`$ kubectl get pods -n prod
NAME                  READY   STATUS             RESTARTS      AGE
api-7d9f8c6b5-x2k4p   0/1     CrashLoopBackOff   9 (40s ago)   6m12s

$ kubectl describe pod api-7d9f8c6b5-x2k4p -n prod
Name:         api-7d9f8c6b5-x2k4p
Namespace:    prod
Containers:
  api:
    Image:          myorg/api:1.4.2
    State:          Waiting
      Reason:       CrashLoopBackOff
    Last State:     Terminated
      Reason:       Error
      Exit Code:    1
    Restart Count:  9
Events:
  Type     Reason   Age                From     Message
  ----     ------   ----               ----     -------
  Normal   Started  2m (x4 over 3m)    kubelet  Started container api
  Warning  BackOff  40s (x9 over 3m)   kubelet  Back-off restarting failed container api in pod api-7d9f8c6b5-x2k4p_prod

$ kubectl logs api-7d9f8c6b5-x2k4p -n prod --previous
Traceback (most recent call last):
  File "/app/main.py", line 12, in <module>
    DATABASE_URL = os.environ["DATABASE_URL"]
KeyError: 'DATABASE_URL'`,
  },
  {
    id: "aws",
    label: "AWS AccessDenied",
    category: "AWS",
    log: String.raw`$ aws sts get-caller-identity
{
    "UserId": "AROAEXAMPLEID:GitHubActions",
    "Account": "123456789012",
    "Arn": "arn:aws:sts::123456789012:assumed-role/ci-deploy-role/GitHubActions"
}

$ aws s3 cp build.zip s3://deploydoctor-artifacts/releases/build.zip
upload failed: ./build.zip to s3://deploydoctor-artifacts/releases/build.zip An error occurred (AccessDenied) when calling the PutObject operation: User: arn:aws:sts::123456789012:assumed-role/ci-deploy-role/GitHubActions is not authorized to perform: s3:PutObject on resource: "arn:aws:s3:::deploydoctor-artifacts/releases/build.zip" because no identity-based policy allows the s3:PutObject action
Error: Process completed with exit code 1.`,
  },
  {
    id: "terraform",
    label: "Terraform state lock",
    category: "Terraform",
    log: String.raw`$ terraform apply -auto-approve
Acquiring state lock. This may take a few moments...
╷
│ Error: Error acquiring the state lock
│
│ Error message: operation error DynamoDB: PutItem, https response error
│ StatusCode: 400, RequestID: 8F2K1EXAMPLE, ConditionalCheckFailedException:
│ The conditional request failed
│ Lock Info:
│   ID:        6f1d2c3a-8b7e-4a55-9c1d-0e2f4a6b8c10
│   Path:      deploydoctor-tfstate/prod/terraform.tfstate
│   Operation: OperationTypeApply
│   Who:       runner@ci-runner-42
│   Version:   1.9.5
│   Created:   2026-10-05 08:12:41.220184 +0000 UTC
│   Info:
│
│ Terraform acquires a state lock to protect the state from being written
│ by multiple users at the same time. Please resolve the issue above and try
│ again. For most commands, you can disable locking with the "-lock=false"
│ flag, but this is not recommended.
╵`,
  },
  {
    id: "cicd",
    label: "CI/CD deploy failure",
    category: "CI/CD",
    log: String.raw`Run eb deploy deploydoctor-prod --staged
Creating application version archive "app-261005_081200".
Uploading: [##################################################] 100% Done...
2026-10-05 08:12:44    INFO    Environment update is starting.
2026-10-05 08:12:58    INFO    Deploying new version to instance(s).
2026-10-05 08:13:58    ERROR   Instance deployment: Both 'Dockerfile' and 'Dockerrun.aws.json' are missing in your source bundle. Include at least one of them in your source bundle. The deployment failed.
2026-10-05 08:13:58    ERROR   Instance deployment failed. For details, see 'eb-engine.log'.
2026-10-05 08:14:01    ERROR   Unsuccessful command execution on instance id(s) 'i-0a1b2c3d4e5f60718'. Aborting the operation.
2026-10-05 08:14:01    ERROR   Failed to deploy application.
Error: Process completed with exit code 1.`,
  },
  {
    id: "postgres",
    label: "PostgreSQL timeout",
    category: "Database",
    log: String.raw`2026-10-05 08:21:07,412 INFO  Starting application, running database migrations
Traceback (most recent call last):
  File "/app/.venv/lib/python3.12/site-packages/sqlalchemy/engine/base.py", line 146, in __init__
    self._dbapi_connection = engine.raw_connection()
  File "/app/.venv/lib/python3.12/site-packages/psycopg2/__init__.py", line 122, in connect
    conn = _connect(dsn, connection_factory=connection_factory, **kwasync)
psycopg2.OperationalError: connection to server at "deploydoctor-db.c9x2example.ap-south-1.rds.amazonaws.com" (10.0.12.34), port 5432 failed: Connection timed out
	Is the server running on that host and accepting TCP/IP connections?

The above exception was the direct cause of the following exception:

sqlalchemy.exc.OperationalError: (psycopg2.OperationalError) connection to server at "deploydoctor-db.c9x2example.ap-south-1.rds.amazonaws.com" (10.0.12.34), port 5432 failed: Connection timed out
(Background on this error at: https://sqlalche.me/e/20/e3q8)
2026-10-05 08:21:37,498 ERROR Application startup failed. Exiting.`,
  },
  {
    id: "nginx",
    label: "Nginx 502",
    category: "Networking",
    log: String.raw`2026/10/05 08:21:07 [error] 29#29: *412 connect() failed (111: Connection refused) while connecting to upstream, client: 203.0.113.24, server: , request: "GET /health HTTP/1.1", upstream: "http://172.17.0.2:8000/health", host: "deploydoctor-prod.ap-south-1.elasticbeanstalk.com"
2026/10/05 08:21:09 [error] 29#29: *414 connect() failed (111: Connection refused) while connecting to upstream, client: 203.0.113.24, server: , request: "GET / HTTP/1.1", upstream: "http://172.17.0.2:8000/", host: "deploydoctor-prod.ap-south-1.elasticbeanstalk.com"
203.0.113.24 - - [05/Oct/2026:08:21:09 +0000] "GET / HTTP/1.1" 502 150 "-" "Mozilla/5.0" "-"
2026/10/05 08:21:15 [error] 29#29: *418 connect() failed (111: Connection refused) while connecting to upstream, client: 10.0.1.55, server: , request: "GET /health HTTP/1.1", upstream: "http://172.17.0.2:8000/health", host: "10.0.1.20"
10.0.1.55 - - [05/Oct/2026:08:21:15 +0000] "GET /health HTTP/1.1" 502 150 "-" "ELB-HealthChecker/2.0" "-"`,
  },
]);
