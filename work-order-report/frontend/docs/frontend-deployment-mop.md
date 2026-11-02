# MOP: ITIL Group Reports Frontend Production Deployment

**Document reference:** MOP-ITIL-FE-001  
**Application:** ITIL Group Reports Automation - Next.js frontend  
**Target environment:** Production (first deployment)  
**Deployment owner:** Application team  
**Infrastructure model:** Rootless Podman with Nginx ingress  
**Reference environment:** QA

## 1. Purpose and scope

This document defines the production prerequisites and deployment method for the
frontend. Production should mirror the proven QA layout as closely as possible.

Infrastructure prepares the host, service account, storage, network, DNS, TLS,
and Nginx. The application team supplies and deploys the approved application
release. Infrastructure is not expected to build or modify application source.

Production-specific values that are not yet allocated are intentionally blank in
Section 3. Infrastructure should complete and return that section before the
deployment session.

## 2. Target architecture

```text
User browser
    |
    | HTTPS 443
    v
Nginx (production FQDN and TLS)
    |
    | HTTP to 127.0.0.1:3001
    v
Next.js frontend container (rootless Podman, port 3000)
    |
    | /api/* over Podman network "itil-net"
    v
FastAPI backend container (port 8000, not publicly exposed)
    |
    v
PostgreSQL container (port 5432, internal only)
```

Browser requests remain same-origin. The frontend sends requests to `/api/v1/*`;
the Next.js server proxies them to the backend origin configured when the
frontend release is built. Browser-to-backend CORS is therefore not required for
the normal production path.

## 3. Production values to be completed by Infrastructure

| Item | Production value |
| --- | --- |
| Linux hostname | ______________________________ |
| Server IP | ______________________________ |
| Rootless service account | `svc_itil_reports` / __________________ |
| Public frontend FQDN | ______________________________ |
| DNS change owner/reference | ______________________________ |
| TLS certificate owner/reference | ______________________________ |
| Nginx configuration owner | ______________________________ |
| Approved deployment workstation/source | ______________________________ |
| Approved container registry or image-transfer method | ______________________________ |
| Backup retention period | ______________________________ |
| Monitoring/alerting destination | ______________________________ |

The backend origin is not an Infrastructure-selected public URL. The application
team will set it after the backend is deployed. When both containers use
`itil-net`, the intended value is:

```text
http://itil-backend-api:8000
```

The frontend public hostname must never be used as `API_PROXY_URL`; doing so can
create a recursive `/api` proxy loop.

## 4. Infrastructure prerequisites

### 4.1 Host and service account

- Supported production Linux distribution.
- Rootless Podman 4.x or later for the dedicated service account.
- `loginctl enable-linger <service-account>` so containers survive logout and
  can start after host reboot.
- Subordinate UID/GID mappings configured where required.
- `bash`, `curl`, `tar`, `gzip`, `ca-certificates`, and an approved SSH/SFTP
  transfer mechanism.
- NTP enabled and timezone set to `Africa/Johannesburg`.
- SSH access from the approved deployment workstation.
- No application container may run as a personal user in production.

Validation:

```bash
id
podman --version
podman info --format '{{.Host.Security.Rootless}}'
loginctl show-user "$USER" -p Linger
```

Expected values are the production service account, `true` for rootless, and
`Linger=yes`.

### 4.2 Directories and permissions

Create the shared layout used by QA:

```bash
sudo mkdir -p /opt/itil-report-stack/frontend
sudo mkdir -p /opt/itil-report-stack/releases
sudo mkdir -p /opt/itil-report-stack/shared
sudo mkdir -p /opt/itil-report-stack/scripts
sudo chown -R <service-account>:<service-account> /opt/itil-report-stack
sudo chmod 750 /opt/itil-report-stack
```

Frontend releases use:

```text
/opt/itil-report-stack/frontend/releases/<release-tag>/
/opt/itil-report-stack/frontend/current -> releases/<release-tag>/
```

Retain at least one previously verified frontend release after each upgrade.

### 4.3 Podman network

The application team creates the shared rootless bridge network if it does not
exist:

```bash
podman network inspect itil-net >/dev/null 2>&1 ||
  podman network create itil-net
```

The frontend, backend, and PostgreSQL containers must be created by the same
rootless service account to use this network consistently.

### 4.4 Network and firewall

| Direction | Port | Source/destination | Purpose |
| --- | ---: | --- | --- |
| Inbound | TCP 22 | Approved admin/deployment workstation | Deployment |
| Inbound | TCP 443 | Approved user networks | Nginx HTTPS |
| Inbound | TCP 80 | Approved user networks | Optional HTTPS redirect only |
| Host-local | TCP 3001 | `127.0.0.1` only | Nginx to frontend |
| Container internal | TCP 8000 | Frontend to backend on `itil-net` | API |
| Container internal | TCP 5432 | Backend to PostgreSQL on `itil-net` | Database |
| Outbound | TCP 443 | Approved registry | Image access, if used |

Ports `3001`, `8000`, and `5432` must not be exposed to user networks.

## 5. Nginx requirement

Infrastructure should create a production server block using the completed FQDN
and approved TLS certificate:

```nginx
server {
    listen 80;
    server_name <production-frontend-fqdn>;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name <production-frontend-fqdn>;

    ssl_certificate     <approved-certificate-path>;
    ssl_certificate_key <approved-private-key-path>;

    client_max_body_size 20m;

    location / {
        proxy_pass http://127.0.0.1:3001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 120s;
    }
}
```

Infrastructure may add approved security headers and corporate TLS standards.
Do not cache `/api/*`, login responses, or authenticated HTML.

Validate before go-live:

```bash
sudo nginx -t
curl --fail --resolve <production-frontend-fqdn>:443:127.0.0.1 \
  https://<production-frontend-fqdn>/healthz
```

## 6. Release preparation

The release must:

- Be built from the approved source revision.
- Pass `npm run type-check`, `npm run lint`, and `npm run build`.
- Be built for Linux using the repository Dockerfile or an approved Linux CI
  runner. Do not deploy a Windows-built `node_modules` bundle to Linux.
- Use `NEXT_PUBLIC_API_URL` as an empty value so browser calls remain
  same-origin.
- Use the application-team-confirmed internal backend origin for
  `API_PROXY_URL`.
- Record the source revision, release tag, build time, and image/archive
  checksum in the change record.

The repository Dockerfile (`node:22-bookworm-slim`) is the authoritative
frontend runtime. Production should not substitute `node:22-alpine` for a
standalone bundle built on another operating system.

`deploy-frontend.ps1` remains the proven QA archive workflow and is deliberately
blocked for PROD. The first production deployment must follow this image-based
procedure until a production pipeline is approved and tested.

Example image build after the backend origin is confirmed:

```bash
podman build \
  --build-arg NEXT_PUBLIC_API_URL= \
  --build-arg API_PROXY_URL=http://itil-backend-api:8000 \
  --tag localhost/itil-frontend-ui:<release-tag> \
  .
```

## 7. First production deployment

Run as the rootless production service account:

```bash
podman network inspect itil-net >/dev/null 2>&1 ||
  podman network create itil-net

podman run -d \
  --name itil-frontend-ui \
  --network itil-net \
  --restart unless-stopped \
  --publish 127.0.0.1:3001:3000 \
  --env NODE_ENV=production \
  --env PORT=3000 \
  --env HOSTNAME=0.0.0.0 \
  localhost/itil-frontend-ui:<release-tag>
```

The image contains a health check for `/healthz`. Confirm:

```bash
podman ps --filter name=itil-frontend-ui
podman inspect itil-frontend-ui \
  --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}'
podman logs --tail 100 itil-frontend-ui
curl --fail http://127.0.0.1:3001/healthz
```

Then validate through Nginx:

```bash
curl --fail https://<production-frontend-fqdn>/healthz
curl --fail https://<production-frontend-fqdn>/api/v1/health
```

The second command proves the complete Nginx -> frontend -> backend path.

## 8. Functional validation

During the approved deployment window, the application team will verify:

- Login using the temporary production Super Admin account.
- Forced password rotation.
- Workspace, SLA Monitor, Daily Report, and Raw Reports pages.
- Division and assignee-group data.
- Backend health and latest pipeline status.
- An authorised report generation test.
- No QA hostname, IP, credential, or data appears in production.
- Browser developer tools show `/api/v1/*` calls to the production frontend
  origin, with no CORS failures or proxy loops.

Email and reminder automation must remain disabled until their separate
production approval and controlled send test are complete.

## 9. Rollback

Before deployment, confirm the previous image exists:

```bash
podman image exists localhost/itil-frontend-ui:<previous-release-tag>
```

Rollback:

```bash
podman stop itil-frontend-ui
podman rm itil-frontend-ui

podman run -d \
  --name itil-frontend-ui \
  --network itil-net \
  --restart unless-stopped \
  --publish 127.0.0.1:3001:3000 \
  --env NODE_ENV=production \
  --env PORT=3000 \
  --env HOSTNAME=0.0.0.0 \
  localhost/itil-frontend-ui:<previous-release-tag>

curl --fail http://127.0.0.1:3001/healthz
curl --fail https://<production-frontend-fqdn>/healthz
```

The frontend has no database migration and can be rolled back independently,
provided the selected frontend release remains API-compatible with the deployed
backend.

## 10. Monitoring and handover

Infrastructure should monitor:

- HTTPS availability of `https://<production-frontend-fqdn>/healthz`.
- Nginx 5xx response rate.
- Rootless container state/restarts.
- Host disk usage.
- TLS certificate expiry.

Application logs:

```bash
podman logs --since 30m itil-frontend-ui
```

The final operations handover must record the application owner, Infra support
group, monitoring destination, escalation route, backup retention, production
URL, and approved release tag.

## 11. Readiness checklist

- [ ] Section 3 production values completed by Infrastructure.
- [ ] Rootless Podman verified for the production service account.
- [ ] User lingering enabled for rootless container restart.
- [ ] Shared `itil-net` design approved.
- [ ] Required directories created with correct ownership.
- [ ] DNS and TLS configured.
- [ ] Nginx configuration installed and `nginx -t` passes.
- [ ] Only TCP 443 (and optional redirect port 80) exposed to users.
- [ ] Backend internal origin confirmed by the application team.
- [ ] Approved Linux-built frontend image available with checksum.
- [ ] Backend deployed and healthy before frontend functional validation.
- [ ] Monitoring and alert routing configured.
- [ ] Rollback image retained and rollback command reviewed.
- [ ] Change window and application validation participants confirmed.
