/* Sample logs for the demo. All data is fictional (documentation IPs, example AWS account). */
window.SAMPLE_LOGS = [
  {
    id: "docker",
    label: "Docker build",
    category: "Docker",
    log: `[+] Building 14.2s (9/12)
 => [internal] load build definition from Dockerfile
 => [internal] load metadata for docker.io/library/python:3.12-slim
 => [1/6] FROM docker.io/library/python:3.12-slim
 => [3/6] COPY requirements.txt .
 => ERROR [4/6] RUN pip install --no-cache-dir -r requirements.txt
------
 > [4/6] RUN pip install --no-cache-dir -r requirements.txt:
#9 3.114 Collecting psycopg2==2.9.9
#9 3.402   Downloading psycopg2-2.9.9.tar.gz (384 kB)
#9 4.871   error: subprocess-exited-with-error
#9 4.871   x python setup.py egg_info did not run successfully.
#9 4.871   Error: pg_config executable not found.
#9 4.871   pg_config is required to build psycopg2 from source.
#9 4.871   Please add the directory containing pg_config to the PATH
#9 4.871   or specify the full executable path with the option.
------
Dockerfile:6
--------------------
   5 |     COPY requirements.txt .
   6 | >>> RUN pip install --no-cache-dir -r requirements.txt
   7 |     COPY . .
--------------------
ERROR: failed to solve: process "/bin/sh -c pip install --no-cache-dir -r requirements.txt" did not complete successfully: exit code: 1`,
  },
  {
    id: "kubernetes",
    label: "Kubernetes CrashLoopBackOff",
    category: "Kubernetes",
    log: `$ kubectl get pods -n prod
NAME                   READY   STATUS             RESTARTS      AGE
api-7d9f8c6b5-x2k4p    0/1     CrashLoopBackOff   9 (40s ago)   3m

$ kubectl describe pod api-7d9f8c6b5-x2k4p -n prod
Events:
  Type     Reason     Age                From               Message
  ----     ------     ----               ----               -------
  Normal   Scheduled  3m                 default-scheduler  Successfully assigned prod/api-7d9f8c6b5-x2k4p to node-1
  Normal   Pulled     2m (x4 over 3m)    kubelet            Container image "myorg/api:1.4.2" already present on machine
  Normal   Created    2m (x4 over 3m)    kubelet            Created container api
  Normal   Started    2m (x4 over 3m)    kubelet            Started container api
  Warning  BackOff    40s (x9 over 3m)   kubelet            Back-off restarting failed container api in pod api-7d9f8c6b5-x2k4p_prod

$ kubectl logs api-7d9f8c6b5-x2k4p -n prod --previous
Traceback (most recent call last):
  File "/app/main.py", line 12, in <module>
    DATABASE_URL = os.environ["DATABASE_URL"]
KeyError: 'DATABASE_URL'

Last State:  Terminated
  Reason:    Error
  Exit Code: 1`,
  },
  {
    id: "aws",
    label: "AWS permission error",
    category: "AWS",
    log: `$ eb deploy deploydoctor-prod
Creating application version archive "app-261005_101530".
Uploading deploydoctor/app-261005_101530.zip to S3. This may take a while.

An error occurred (AccessDenied) when calling the PutObject operation: User: arn:aws:iam::123456789012:user/ci-deployer is not authorized to perform: s3:PutObject on resource: "arn:aws:s3:::elasticbeanstalk-ap-south-1-123456789012/deploydoctor/app-261005_101530.zip" because no identity-based policy allows the s3:PutObject action

ERROR: Failed to upload application version to S3.
ERROR: Deployment aborted. The environment was not modified.`,
  },
  {
    id: "terraform",
    label: "Terraform state lock",
    category: "Terraform",
    log: `Terraform v1.9.5
on linux_amd64
Initializing the backend...
Successfully configured the backend "s3"!
Acquiring state lock. This may take a few moments...
╷
│ Error: Error acquiring the state lock
│
│ Error message: operation error DynamoDB: PutItem, https response error
│ StatusCode: 400, RequestID: 7K2D9F1QJ8, ConditionalCheckFailedException: The
│ conditional request failed
│ Lock Info:
│   ID:        3f6a9c1e-52b7-9a40-1c3d-8e7f60b4a2d1
│   Path:      deploydoctor-tfstate/prod/terraform.tfstate
│   Operation: OperationTypeApply
│   Who:       ci-runner@build-agent-7
│   Version:   1.9.5
│   Created:   2026-10-05 09:12:41.220331 +0000 UTC
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
    log: `##[group]Run actions/checkout@v4
##[endgroup]
##[group]Run pip install -r backend/requirements-dev.txt
Successfully installed fastapi-0.115.6 pytest-8.3.4 ruff-0.8.4
##[endgroup]
##[group]Run ruff check backend
All checks passed!
##[endgroup]
##[group]Run pytest backend/tests
============================== 14 passed in 3.82s ==============================
##[endgroup]
##[group]Run aws-actions/configure-aws-credentials@v4
##[endgroup]
##[error]Credentials could not be loaded, please check your action inputs: Could not load credentials from any providers
Post job cleanup.
##[error]Process completed with exit code 1.
Deploy job: failed`,
  },
  {
    id: "postgres",
    label: "PostgreSQL connection",
    category: "Database",
    log: `INFO:     Started server process [1]
INFO:     Waiting for application startup.
ERROR:    Traceback (most recent call last):
  File "/app/app/database.py", line 31, in check_database
    conn.execute(text("SELECT 1"))
sqlalchemy.exc.OperationalError: (psycopg2.OperationalError) connection to server at "deploydoctor.c9x2abcd1234.ap-south-1.rds.amazonaws.com" (10.0.12.45), port 5432 failed: Connection timed out
    Is the server running on that host and accepting TCP/IP connections?
(Background on this error at: https://sqlalche.me/e/20/e3q8)

ERROR:    Application startup failed. Exiting.`,
  },
  {
    id: "nginx",
    label: "Nginx 502 error",
    category: "Networking",
    log: `2026/10/05 10:42:13 [error] 29#29: *1847 connect() failed (111: Connection refused) while connecting to upstream, client: 203.0.113.24, server: _, request: "GET /health HTTP/1.1", upstream: "http://127.0.0.1:8000/health", host: "app.example.com"
2026/10/05 10:42:14 [error] 29#29: *1849 connect() failed (111: Connection refused) while connecting to upstream, client: 203.0.113.24, server: _, request: "GET / HTTP/1.1", upstream: "http://127.0.0.1:8000/", host: "app.example.com"
2026/10/05 10:42:19 [error] 29#29: *1853 connect() failed (111: Connection refused) while connecting to upstream, client: 198.51.100.7, server: _, request: "POST /api/analyze HTTP/1.1", upstream: "http://127.0.0.1:8000/api/analyze", host: "app.example.com"
203.0.113.24 - - [05/Oct/2026:10:42:13 +0000] "GET /health HTTP/1.1" 502 157 "-" "ELB-HealthChecker/2.0"
203.0.113.24 - - [05/Oct/2026:10:42:14 +0000] "GET / HTTP/1.1" 502 157 "-" "Mozilla/5.0"`,
  },
];
