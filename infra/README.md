# Infrastructure

Terraform in two layers, applied with the personal gcloud account:

```bash
export GOOGLE_OAUTH_ACCESS_TOKEN=$(gcloud auth print-access-token)
```

- `bootstrap/` (local state, run once): project, billing link, remote-state bucket, budget alert.
- `main/` (GCS state): APIs, Artifact Registry, attachments bucket, Secret Manager, service accounts, Cloud Run, GitHub Workload Identity Federation.

Secret values are added outside Terraform so they never land in state:

```bash
printf '%s' "$VALUE" | gcloud secrets versions add anthropic-api-key --data-file=-
```

Cloud Run is created once every secret has a version: set `deploy_service = true`.

Tear down: `terraform destroy` in `main/`, then `bootstrap/`.
