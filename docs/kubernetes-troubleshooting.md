# Kubernetes troubleshooting

OpsDesk was my project for learning Kubernetes. The app worked locally, but getting it
running on a cluster surfaced a handful of problems. This page records each one: what I
saw, how I narrowed it down with `kubectl`, what the cause was, and what fixed it.

All resources live in the `opsdesk` namespace, so every command below passes `-n opsdesk`.

## The debugging loop

Almost every problem was found with the same four commands, in this order:

```bash
# 1. Which pods are unhealthy? Look at STATUS and RESTARTS.
kubectl get pods -n opsdesk

# 2. Why? The Events section at the bottom explains scheduling, image pulls,
#    missing ConfigMaps/Secrets and why the last container exited.
kubectl describe pod <pod-name> -n opsdesk

# 3. What did the app print before it died?
kubectl logs <pod-name> -n opsdesk
kubectl logs <pod-name> -n opsdesk --previous   # logs from the crashed container, not the restarted one

# 4. Does the thing it's trying to reach exist under the name it's using?
kubectl get svc,configmap,secret -n opsdesk
```

A rule of thumb that came out of this: if `describe` shows the container never started
(`CreateContainerConfigError`, `ImagePullBackOff`), the problem is in the manifest. If the
container started and then exited (`CrashLoopBackOff`), the problem is in what the app
received, and `logs --previous` tells you what.

---

## 1. Backend pods crashing: no ConfigMap or Secret loaded

**Symptom.** The `opsdesk-backend` pods went into `CrashLoopBackOff` right after deploying.

**Diagnosis.** `kubectl logs --previous` on a backend pod showed Django failing while it
loaded its settings. The API reads all of its configuration from environment variables
(`DJANGO_SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, `JWT_SIGNING_KEY` and others, see
[`backend/config/settings/base.py`](../backend/config/settings/base.py)), and
`django-environ` raises `ImproperlyConfigured` when a required one is missing. Looking at
the Deployment showed why they were missing: the container had no `env` or `envFrom` at
all, so the ConfigMap and Secret existed in the cluster but were never handed to the pod.

**Fix.** Load both into the container with `envFrom`
([`k8s/backend/deployment.yml`](../k8s/backend/deployment.yml)):

```yaml
containers:
- name: opsdesk-backend
  image: abednegotenge/opsdesk-backend:latest
  envFrom:
    - configMapRef:
        name: opsdesk-config
    - secretRef:
        name: opsdesk-secret
```

### 1b. Follow-up: the ConfigMap name was wrong

**Symptom.** After adding `envFrom`, the new pods didn't crash; they never started. Their
status was `CreateContainerConfigError`.

**Diagnosis.** There are no logs for a container that never started, so `kubectl logs`
had nothing to say. `kubectl describe pod` did: the Events section reported that the
ConfigMap the pod referenced could not be found. The first version of the fix referenced
`opsdesk-configmap`, but [`k8s/config/configmap.yml`](../k8s/config/configmap.yml) names it
`opsdesk-config`. `kubectl get configmap -n opsdesk` shows the real name.

**Fix.** Reference `opsdesk-config`, the name the ConfigMap actually has.

**Lesson.** A reference to a ConfigMap or Secret is just a string. Kubernetes doesn't check
it when you apply the Deployment, only when it tries to start the container. When a pod
is stuck before it starts, read `describe`, not `logs`.

---

## 2. Frontend pods crashing: `nginx.conf` written for Docker Compose

**Symptom.** The `opsdesk-frontend` pods (nginx serving the built React app) went into
`CrashLoopBackOff`.

**Diagnosis.** `kubectl logs --previous` on a frontend pod showed nginx exiting while it
loaded its configuration, before serving anything. The config in
[`frontend/nginx.conf`](../frontend/nginx.conf) had been written for running the stack
with Docker Compose:

```nginx
location /api/ {
    proxy_pass http://api:8000;
    ...
}
```

`api` was the Compose service name. In the cluster there is no Service called `api`; the
backend Service is `opsdesk-backend` on port `5000` (forwarding to the container's
`8000`, see [`k8s/backend/service.yml`](../k8s/backend/service.yml)). nginx resolves the
hostnames in `proxy_pass` when it starts, and if one can't be resolved it refuses to start,
so the container exited and Kubernetes kept restarting it. `kubectl get svc -n opsdesk`
showed the name it should have used.

The same file also had two `location` blocks that could never match, because exact-match
locations need a leading slash:

```nginx
location = "index.html" { ... }   # never matches a request
location = "config.js"  { ... }
```

**Fix.** Point the proxy at the Kubernetes Service and fix the paths:

```nginx
location /api/ {
    proxy_pass http://opsdesk-backend:5000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
}

location = /index.html { add_header Cache-Control "no-cache"; }
location = /config.js  { add_header Cache-Control "no-cache"; }
```

**Lesson.** Inside the cluster, services find each other by Service name through cluster
DNS. Any hostname baked into an image (an nginx upstream, a connection string) has to be a
name that exists as a Service in the same namespace.

---

## 3. "Sign in is temporarily unavailable": Redis Service name mismatch

**Symptom.** Every pod was `Running` and the UI loaded, but signing in with correct
credentials failed with *"Sign in is temporarily unavailable"* (the API returns 503).

**Diagnosis.** Nothing was crashing, so `get pods` looked healthy; this one lived in the
logs. The API stores refresh tokens in Redis, and returns that 503 when Redis can't be
reached. The ConfigMap pointed `REDIS_URL`, `CELERY_BROKER_URL` and `CACHE_URL` at host
`redis` on port `6379`, but `kubectl get svc -n opsdesk` showed the Redis Service was named
`redis-service`. There was no `redis` hostname for the API to connect to.

**Fix.** Rename the Service to `redis` so it matches the ConfigMap
([`k8s/redis/service.yml`](../k8s/redis/service.yml)). The Redis Deployment was also cut
from 2 replicas to 1: two independent Redis pods behind one Service would each hold half of
the refresh tokens, so token refreshes would fail at random.

**Lesson.** Same root cause as issue 2: a hostname in configuration that doesn't match a
Service name. A healthy pod list doesn't mean the pods can reach each other.

---

## 4. Secrets committed to git

**What happened.** The first version of `k8s/secrets/secret.yml`, with real values in it,
was committed and pushed along with the rest of the manifests.

**Fix.**

- Removed the file from the repository and added
  [`k8s/secrets/secret.example.yml`](../k8s/secrets/secret.example.yml), a template with
  placeholder values. The real Secret is created from a local copy that is never committed.
- Rotated every value that had been in the file. Deleting a file only removes it from the
  latest commit; anything that was ever pushed is still in the history, so once a secret
  has been pushed it has to be treated as leaked and replaced.
- Added the local secrets file to `.gitignore` so it can't be committed again by accident.

**Lesson.** Keep a committed template and an ignored real file from day one. A Kubernetes
`Secret` manifest only base64-encodes its `data`, which is encoding, not encryption.

---

## Other fixes along the way

These came up while getting images built and onto the cluster:

- **Frontend image build path.** The frontend Dockerfile copied the built app from
  `/app/dist`, but the build stage writes it to `/build/dist`.
- **Multi-architecture images.** The GitHub Actions workflow now builds images for both
  `linux/amd64` and `linux/arm64` (using QEMU and Buildx), so the same image runs on an
  Apple Silicon machine and on a typical x86 cloud node.
- **Database URL.** The `DATABASE_URL` value in the Secret had to be corrected so the API
  could reach PostgreSQL.

## Quick reference

| What you see | Look here first | Usual cause |
| --- | --- | --- |
| `CrashLoopBackOff` | `kubectl logs <pod> --previous` | App starts and exits: missing env vars, bad config file, unreachable dependency |
| `CreateContainerConfigError` | `kubectl describe pod <pod>` (Events) | Pod references a ConfigMap, Secret or key that doesn't exist |
| `ImagePullBackOff` / `ErrImagePull` | `kubectl describe pod <pod>` (Events) | Wrong image name or tag, private registry, or no image for the node's architecture |
| Pods `Running` but a feature fails | `kubectl logs <pod>` and `kubectl get svc` | A hostname in config doesn't match a Service name |
