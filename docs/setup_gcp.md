# Google Cloud Platform Setup - Command Reference

This document tracks all commands executed during the GCP setup for Orbit Agent deployment.

## ✅ Completed Steps

### Step 1: GCP CLI Authentication

```bash
# Authenticate with Google Cloud
gcloud auth login

# Set environment variables
export PROJECT_ID="orbit-agent"
export REGION="us-central1"
```

---

### Step 2: Create GCP Project

```bash
# Create new GCP project
gcloud projects create $PROJECT_ID --name="Orbit Agent"

# Set as active project
gcloud config set project $PROJECT_ID

# Verify active project
gcloud config get-value project
```

**Result:** Project `orbit-agent` created successfully

---

### Step 3: Enable Billing

```bash
# List billing accounts
gcloud billing accounts list

# Link billing account to project
gcloud billing projects link $PROJECT_ID --billing-account=0145B7-7B3717-3A25E2

# Verify billing is enabled
gcloud billing projects describe $PROJECT_ID
```

**Result:** 
```
billingAccountName: billingAccounts/0145B7-7B3717-3A25E2
billingEnabled: true
projectId: orbit-agent
```

---

### Step 4: Enable Required APIs

```bash
# Enable all necessary Google Cloud APIs
gcloud services enable \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  compute.googleapis.com \
  iam.googleapis.com
```

**Result:** All APIs enabled successfully

---

### Step 5: Create Artifact Registry Repository

```bash
# Create Docker repository for storing images
gcloud artifacts repositories create orbit-agent-repo \
  --repository-format=docker \
  --location=$REGION \
  --description="Docker images for Orbit Agent services"

# Configure Docker authentication
gcloud auth configure-docker ${REGION}-docker.pkg.dev
```

**Result:** Repository created at `us-central1-docker.pkg.dev/orbit-agent/orbit-agent-repo`

---

### Step 6: Create Service Account for GitHub Actions

```bash
# Create service account
gcloud iam service-accounts create github-actions-sa \
  --display-name="GitHub Actions Service Account" \
  --description="Service account for CI/CD deployments from GitHub"

# Set service account email variable
export SA_EMAIL="github-actions-sa@${PROJECT_ID}.iam.gserviceaccount.com"
```

**Result:** Service account created: `github-actions-sa@orbit-agent.iam.gserviceaccount.com`

---

### Step 7: Grant Service Account Permissions

```bash
# Grant Cloud Run admin role
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/run.admin"

# Grant Artifact Registry writer role
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/artifactregistry.writer"

# Grant Service Account User role
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/iam.serviceAccountUser"

# Grant Secret Manager accessor role
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/secretmanager.secretAccessor"
```

**Result:** Service account granted all necessary permissions

---

### Step 8: Create Service Account Key

```bash
# Create and download service account key
gcloud iam service-accounts keys create github-sa-key.json \
  --iam-account=$SA_EMAIL

# View the key (for adding to GitHub secrets)
cat github-sa-key.json
```

**Result:** Key file created at `c:/Users/aryav/projects/orbit-agent/github-sa-key.json`

⚠️ **IMPORTANT:** This file contains sensitive credentials. Do not commit to git.

---

### Step 9: Upload Secrets to Secret Manager

```bash
# Fix line endings in .env file (Windows compatibility)
dos2unix .env

# Run Python script to bulk upload all secrets
python upload-secrets.py
```

**Result:** All 14 environment variables uploaded successfully:
- ✅ GOOGLE_API_KEY
- ✅ GEMINI_API_KEY
- ✅ MODEL_PROVIDER
- ✅ LOG_LEVEL
- ✅ POSTGRES_PASSWORD
- ✅ IN_DOCKER
- ✅ ENV_MODE
- ✅ SUPABASE_URL
- ✅ SUPABASE_ANON_KEY
- ✅ SUPABASE_SERVICE_ROLE_KEY
- ✅ REDIS_HOST
- ✅ REDIS_PORT
- ✅ TAVILY_API_KEY
- ✅ COMPOSIO_API_KEY

**Note:** The `upload-secrets.py` script automatically grants **both service accounts** access to all secrets:
- GitHub Actions SA: `github-actions-sa@orbit-agent.iam.gserviceaccount.com` (for deployments)
- Cloud Run SA: `642172129546-compute@developer.gserviceaccount.com` (for runtime access)

No manual IAM binding needed!

---

## 📋 Verification Commands

### Verify Project Configuration
```bash
# Check current project
gcloud config get-value project

# Check billing status
gcloud billing projects describe $PROJECT_ID
```

### Verify Enabled Services
```bash
gcloud services list --enabled
```

### Verify Artifact Registry
```bash
gcloud artifacts repositories list --location=$REGION
```

### Verify Service Account
```bash
gcloud iam service-accounts list
gcloud projects get-iam-policy $PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:github-actions-sa*"
```

### Verify Secrets
```bash
gcloud secrets list --project=$PROJECT_ID

gcloud secrets describe GOOGLE_API_KEY --project=$PROJECT_ID

gcloud secrets versions access latest --secret=GOOGLE_API_KEY --project=$PROJECT_ID
```

---

## 🔐 Secret Management - Bulk Operations

### Manual IAM Binding (if needed)

If you need to grant access to all existing secrets manually:

```bash
# Grant service account access to ALL existing secrets
for secret in $(gcloud secrets list --format="value(name)" --project=$PROJECT_ID); do
  echo "Granting access to $secret..."
  gcloud secrets add-iam-policy-binding $secret \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/secretmanager.secretAccessor" \
    --project=$PROJECT_ID
done
```

### Add New Secret Manually

```bash
# Create a new secret
echo -n "your-secret-value" | gcloud secrets create NEW_SECRET_NAME --data-file=-

# Grant service account access
gcloud secrets add-iam-policy-binding NEW_SECRET_NAME \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/secretmanager.secretAccessor"
```

---

## 🗑️ Cleanup Commands (If Needed)

### Delete Secrets
```bash
# Delete a specific secret
gcloud secrets delete SECRET_NAME --project=$PROJECT_ID

# Delete all secrets (use with caution!)
for secret in $(gcloud secrets list --format="value(name)" --project=$PROJECT_ID); do
  gcloud secrets delete $secret --quiet --project=$PROJECT_ID
done
```

### Delete Service Account Key
```bash
# List keys
gcloud iam service-accounts keys list --iam-account=$SA_EMAIL

# Delete a specific key
gcloud iam service-accounts keys delete KEY_ID --iam-account=$SA_EMAIL
```

### Delete Service Account
```bash
gcloud iam service-accounts delete $SA_EMAIL --project=$PROJECT_ID
```

### Delete Artifact Registry Repository
```bash
gcloud artifacts repositories delete orbit-agent-repo \
  --location=$REGION \
  --project=$PROJECT_ID
```

---

## 📊 Cost Tracking

### Current Resources
- **Cloud Run:** Not yet deployed (will be ~$10-30/month)
- **Artifact Registry:** ~$1-5/month for storage
- **Secret Manager:** 14 secrets × $0.06 = ~$0.84/month
- **Total Estimated:** ~$12-36/month (depending on traffic)

---

## 🚀 Next Steps

Phase 1 (GCP Setup) is complete! ✅

**Next: Phase 2 - GitHub Repository Setup**

1. Add GitHub secrets (GCP credentials)
2. Create GitHub Actions workflows
3. Deploy to Cloud Run

See [setup_github.md](./setup_github.md) for next steps.

---

## 🔧 Environment Variables Reference

**Local Development:**
```bash
export PROJECT_ID="orbit-agent"
export REGION="us-central1"
export SA_EMAIL="github-actions-sa@orbit-agent.iam.gserviceaccount.com"
```

These should be set in each new terminal session when working with GCP.
