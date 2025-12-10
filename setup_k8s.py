#!/usr/bin/env python3
"""
🚀 Orbit Agent - Complete GKE Setup Automation

This script does EVERYTHING:
1. Creates GKE cluster
2. Creates service accounts (GCP + GitHub Actions)
3. Sets up Workload Identity
4. Creates Kubernetes RBAC
5. Pushes secrets to GitHub
6. Applies K8s manifests

Prerequisites (one-time):
- gcloud auth login
- gh auth login (GitHub CLI)
- Enable APIs: gcloud services enable container.googleapis.com

Usage:
    python setup_complete_k8s.py
"""

import subprocess
import sys
import json
import time
from pathlib import Path
import shutil

# ============================================================================
# CONFIGURATION (Edit these if needed)
# ============================================================================

# ⚠️  IMPORTANT: If you change PROJECT_ID, NAMESPACE, or naming below,
# you MUST also manually update the k8s/*.yaml files to match!
# The script will remind you before applying manifests.

PROJECT_ID = "doot-agent"
REGION = "us-central1"
ZONE = "us-central1-a"
CLUSTER_NAME = "doot-cluster"
NAMESPACE = "doot-agent"

# Service Accounts
GITHUB_SA_NAME = "github-actions-sa"
BROWSER_MANAGER_SA_NAME = "browser-manager-sa"
AGENT_PLATFORM_SA_NAME = "agent-platform-sa"

# GitHub
GITHUB_REPO = "Veer376/doot-agent"

# Registry
REGISTRY = f"{REGION}-docker.pkg.dev"
REPOSITORY = "doot-agent-repo"

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def run_command(cmd, description, check=True, capture_output=False):
    """Run shell command with pretty output."""
    print(f"\n{'='*70}")
    print(f"📌 {description}")
    print(f"{'='*70}")
    print(f"$ {cmd}\n")
    
    result = subprocess.run(
        cmd,
        shell=True,
        check=False,
        capture_output=capture_output,
        text=True
    )
    
    if result.returncode != 0:
        if check:
            print(f"❌ Failed: {description}")
            print(f"Error: {result.stderr if capture_output else 'See output above'}")
            sys.exit(1)
        else:
            print(f"⚠️  Warning: {description} (continuing anyway)")
            return None
    else:
        print(f"✅ Success: {description}")
        return result.stdout if capture_output else None

def check_prerequisite(cmd, name):
    """Check if a command exists."""
    # First try a fast PATH check
    path = shutil.which(cmd)
    if path:
        print(f"✅ {name} found at: {path}")
        return True

    # Fallback: try running `<cmd> --version` (some tools may not be on PATH in certain shells)
    try:
        result = subprocess.run(
            f"{cmd} --version",
            shell=True,
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        result = None

    if result and result.returncode == 0:
        # Print first line of output to show version info
        out = (result.stdout or result.stderr or "").splitlines()
        ver = out[0] if out else "(version info)"
        print(f"✅ {name} available: {ver}")
        return True

    print(f"❌ {name} not found. Please install it first.")
    return False

def confirm(message):
    """Ask user for confirmation."""
    response = input(f"\n🤔 {message} (y/n): ").strip().lower()
    return response == 'y'

# ============================================================================
# MAIN SETUP FUNCTIONS
# ============================================================================

def step_1_check_prerequisites():
    """Check all prerequisites."""
    print("\n" + "="*70)
    print("STEP 1: Checking Prerequisites")
    print("="*70)
    
    prerequisites = [
        ("gcloud", "Google Cloud SDK"),
        ("kubectl", "Kubernetes CLI"),
        ("gh", "GitHub CLI"),
        ("docker", "Docker"),
    ]
    
    all_good = True
    for cmd, name in prerequisites:
        if check_prerequisite(cmd, name):
            print(f"✅ {name} found")
        else:
            all_good = False
    
    if not all_good:
        print("\n❌ Missing prerequisites. Please install them first.")
        sys.exit(1)
    
    # Check gcloud auth
    result = subprocess.run(
        "gcloud auth list --filter=status:ACTIVE --format='value(account)'",
        shell=True,
        capture_output=True,
        text=True
    )
    
    # Also try without format filter (more robust for different gcloud versions)
    if result.returncode != 0 or not result.stdout.strip():
        result2 = subprocess.run(
            "gcloud config get-value account",
            shell=True,
            capture_output=True,
            text=True
        )
        if result2.returncode == 0 and result2.stdout.strip() and result2.stdout.strip() != "(unset)":
            print(f"✅ Authenticated to GCP as: {result2.stdout.strip()}")
        else:
            print("\n❌ Not authenticated to GCP. Run: gcloud auth login")
            sys.exit(1)
    else:
        print(f"✅ Authenticated to GCP as: {result.stdout.strip()}")
    
    # Check gh auth
    result = subprocess.run(
        "gh auth status",
        shell=True,
        check=False,
        capture_output=True
    )
    
    if result.returncode != 0:
        print("\n❌ Not authenticated to GitHub. Run: gh auth login")
        sys.exit(1)
    
    print(f"✅ Authenticated to GitHub")
    
    print("\n✅ All prerequisites met!")

def step_1b_check_or_create_project():
    """Check if GCP project exists, offer to create if missing."""
    print("\n" + "="*70)
    print("STEP 1b: Checking GCP Project & Billing")
    print("="*70)
    
    # Check if project exists AND is active (not deleted)
    result = subprocess.run(
        f"gcloud projects describe {PROJECT_ID} --format='value(lifecycleState)'",
        shell=True,
        capture_output=True,
        text=True
    )
    
    lifecycle_state = result.stdout.strip() if result.returncode == 0 else None
    
    if result.returncode == 0 and lifecycle_state == "ACTIVE":
        print(f"✅ Project '{PROJECT_ID}' exists and is active")
        
        # Check if billing is enabled
        print("\n📌 Checking billing status...")
        billing_result = subprocess.run(
            f"gcloud beta billing projects describe {PROJECT_ID} --format='value(billingAccountName)'",
            shell=True,
            capture_output=True,
            text=True
        )
        
        if billing_result.returncode == 0 and billing_result.stdout.strip():
            billing_account = billing_result.stdout.strip().split('/')[-1]
            print(f"✅ Billing enabled: {billing_account}")
            return
        else:
            print(f"⚠️  Project exists but billing is NOT enabled!")
            print(f"\n⚠️  ERROR: GCP requires billing to be enabled before using GKE, Artifact Registry, etc.")
            
            if not confirm("Link billing account now?"):
                print("\n❌ Billing required. Please enable billing manually:")
                print(f"   1. Go to: https://console.cloud.google.com/billing/linkedaccount?project={PROJECT_ID}")
                print(f"   2. Link a billing account")
                print(f"   3. Re-run this script")
                sys.exit(1)
            
            # Show billing accounts and link
            print("\n📋 Available billing accounts:")
            print("-" * 70)
            subprocess.run("gcloud beta billing accounts list", shell=True)
            print("-" * 70)
            
            billing_account = input("\n🤔 Enter billing account ID (format: XXXXXX-XXXXXX-XXXXXX): ").strip()
            
            if not billing_account:
                print("\n❌ Billing account ID required. Exiting.")
                sys.exit(1)
            
            result = subprocess.run(
                f"gcloud beta billing projects link {PROJECT_ID} --billing-account={billing_account}",
                shell=True,
                check=False
            )
            
            if result.returncode != 0:
                print(f"\n❌ Billing link failed. Link manually:")
                print(f"   1. Go to: https://console.cloud.google.com/billing/linkedaccount?project={PROJECT_ID}")
                print(f"   2. Link billing account: {billing_account}")
                print(f"   3. Re-run this script")
                sys.exit(1)
            
            print(f"✅ Billing linked to project '{PROJECT_ID}'")
            return
    
    # Project doesn't exist
    print(f"⚠️  Project '{PROJECT_ID}' not detected via gcloud projects describe")
    print("\nPossible reasons:")
    print("  1. Project exists but you don't have access")
    print("  2. Project ID is being cached")
    print("  3. Need to create a new project")
    
    if not confirm(f"Try to create project '{PROJECT_ID}'?"):
        print("\n⏭️  Skipping project creation.")
        print("   Assuming project exists and continuing...")
        print("   If APIs fail to enable, the project may not actually exist.\n")
        return
    
    # Create project
    print(f"\n📌 Creating project '{PROJECT_ID}'...")
    result = subprocess.run(
        f"gcloud projects create {PROJECT_ID} --name='{PROJECT_ID}'",
        shell=True,
        check=False
    )
    
    if result.returncode != 0:
        print(f"\n❌ Failed to create project. You may need to:")
        print(f"   - Have permission to create projects")
        print(f"   - Use a unique project ID ('{PROJECT_ID}' may be taken)")
        print(f"\nManual creation:")
        print(f"   1. Go to: https://console.cloud.google.com/projectcreate")
        print(f"   2. Create project with a unique ID")
        print(f"   3. Update PROJECT_ID at top of this script")
        print(f"   4. Re-run this script")
        sys.exit(1)
    
    print(f"✅ Project '{PROJECT_ID}' created")
    
    # Link billing
    print("\n📌 Linking billing account...")
    print("\n📋 Available billing accounts:")
    print("-" * 70)
    subprocess.run("gcloud beta billing accounts list", shell=True)
    print("-" * 70)
    
    billing_account = input("\n🤔 Enter billing account ID (format: XXXXXX-XXXXXX-XXXXXX): ").strip()
    
    if not billing_account:
        print("\n⚠️  Skipping billing setup. You MUST link billing manually:")
        print(f"   1. Go to: https://console.cloud.google.com/billing/linkedaccount?project={PROJECT_ID}")
        print(f"   2. Link a billing account")
        print(f"   3. Re-run this script")
        sys.exit(1)
    
    result = subprocess.run(
        f"gcloud beta billing projects link {PROJECT_ID} --billing-account={billing_account}",
        shell=True,
        check=False
    )
    
    if result.returncode != 0:
        print(f"\n⚠️  Billing link failed. Link manually:")
        print(f"   1. Go to: https://console.cloud.google.com/billing/linkedaccount?project={PROJECT_ID}")
        print(f"   2. Link billing account: {billing_account}")
        print(f"   3. Re-run this script")
        sys.exit(1)
    
    print(f"✅ Billing linked to project '{PROJECT_ID}'")

def step_2_enable_apis():
    """Enable required GCP APIs."""
    print("\n" + "="*70)
    print("STEP 2: Enabling GCP APIs")
    print("="*70)
    
    apis = [
        "container.googleapis.com",          # GKE
        "artifactregistry.googleapis.com",   # Artifact Registry
        "secretmanager.googleapis.com",      # Secret Manager
        "iam.googleapis.com",                # IAM
        "compute.googleapis.com",            # Compute Engine
    ]
    
    for api in apis:
        run_command(
            f"gcloud services enable {api} --project={PROJECT_ID}",
            f"Enabling {api}",
            check=False  # Don't fail if already enabled
        )
    
    print("\n⏳ Waiting 30 seconds for APIs to propagate...")
    time.sleep(30)

def step_3_create_artifact_registry():
    """Create Artifact Registry repository."""
    print("\n" + "="*70)
    print("STEP 3: Creating Artifact Registry")
    print("="*70)
    
    run_command(
        f"gcloud artifacts repositories create {REPOSITORY} \
            --repository-format=docker \
            --location={REGION} \
            --project={PROJECT_ID}",
        "Creating Artifact Registry repository",
        check=False  # Don't fail if already exists
    )

def step_4_create_gke_cluster():
    """Create GKE cluster."""
    print("\n" + "="*70)
    print("STEP 4: Creating GKE Cluster")
    print("="*70)
    
    # Check if cluster already exists
    check_result = subprocess.run(
        f"gcloud container clusters describe {CLUSTER_NAME} --zone={ZONE} --project={PROJECT_ID}",
        shell=True,
        capture_output=True,
        text=True
    )
    
    if check_result.returncode == 0:
        print(f"✅ Cluster '{CLUSTER_NAME}' already exists")
        
        # Configure kubectl to use existing cluster
        run_command(
            f"gcloud container clusters get-credentials {CLUSTER_NAME} \
                --zone={ZONE} \
                --project={PROJECT_ID}",
            "Configuring kubectl"
        )
        return
    
    if not confirm(f"Create GKE cluster '{CLUSTER_NAME}'? (This takes ~5 minutes and costs $$$)"):
        print("⏭️  Skipping cluster creation (assuming it exists)")
        return
    
    run_command(
        f"gcloud container clusters create {CLUSTER_NAME} \
            --zone={ZONE} \
            --project={PROJECT_ID} \
            --num-nodes=2 \
            --machine-type=e2-medium \
            --disk-size=20 \
            --enable-autoscaling \
            --min-nodes=1 \
            --max-nodes=5 \
            --enable-autorepair \
            --enable-autoupgrade \
            --workload-pool={PROJECT_ID}.svc.id.goog",
        "Creating GKE cluster (this takes ~5 minutes)"
    )
    
    # Configure kubectl
    run_command(
        f"gcloud container clusters get-credentials {CLUSTER_NAME} \
            --zone={ZONE} \
            --project={PROJECT_ID}",
        "Configuring kubectl"
    )

def step_5_create_service_accounts():
    """Create GCP service accounts."""
    print("\n" + "="*70)
    print("STEP 5: Creating Service Accounts")
    print("="*70)
    
    # 1. GitHub Actions SA (for CI/CD)
    # Check if already exists
    result = subprocess.run(
        f"gcloud iam service-accounts describe {GITHUB_SA_NAME}@{PROJECT_ID}.iam.gserviceaccount.com --project={PROJECT_ID}",
        shell=True,
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print(f"✅ GitHub Actions service account already exists")
    else:
        run_command(
            f"gcloud iam service-accounts create {GITHUB_SA_NAME} \
                --display-name=\"GitHub Actions Service Account\" \
                --project={PROJECT_ID}",
            "Creating GitHub Actions service account",
            check=True
        )
    
    # Grant permissions to GitHub Actions SA
    github_sa_email = f"{GITHUB_SA_NAME}@{PROJECT_ID}.iam.gserviceaccount.com"
    
    roles = [
        "roles/artifactregistry.writer",     # Push images
        "roles/container.admin",             # Full GKE access (includes RBAC)
        "roles/iam.serviceAccountUser",      # Use service accounts
    ]
    
    for role in roles:
        run_command(
            f'gcloud projects add-iam-policy-binding {PROJECT_ID} '
            f'--member="serviceAccount:{github_sa_email}" '
            f'--role="{role}"',
            f"Granting {role} to GitHub Actions SA",
            check=False
        )
    
    # 2. Browser Manager SA (for Workload Identity)
    # Check if already exists
    result = subprocess.run(
        f"gcloud iam service-accounts describe {BROWSER_MANAGER_SA_NAME}@{PROJECT_ID}.iam.gserviceaccount.com --project={PROJECT_ID}",
        shell=True,
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print(f"✅ Browser Manager service account already exists")
    else:
        run_command(
            f"gcloud iam service-accounts create {BROWSER_MANAGER_SA_NAME} \
                --display-name=\"Browser Manager Service Account\" \
                --project={PROJECT_ID}",
            "Creating Browser Manager service account",
            check=True
        )
    
    # Grant permissions to Browser Manager SA
    browser_sa_email = f"{BROWSER_MANAGER_SA_NAME}@{PROJECT_ID}.iam.gserviceaccount.com"
    
    run_command(
        f'gcloud projects add-iam-policy-binding {PROJECT_ID} '
        f'--member="serviceAccount:{browser_sa_email}" '
        f'--role="roles/artifactregistry.reader"',
        "Granting Artifact Registry Reader to Browser Manager SA",
        check=False
    )
    
    run_command(
        f'gcloud projects add-iam-policy-binding {PROJECT_ID} '
        f'--member="serviceAccount:{browser_sa_email}" '
        f'--role="roles/secretmanager.secretAccessor"',
        "Granting Secret Manager Accessor to Browser Manager SA",
        check=False
    )
    
    # 3. Agent Platform SA (for Workload Identity)
    result = subprocess.run(
        f"gcloud iam service-accounts describe {AGENT_PLATFORM_SA_NAME}@{PROJECT_ID}.iam.gserviceaccount.com --project={PROJECT_ID}",
        shell=True,
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print(f"✅ Agent Platform service account already exists")
    else:
        run_command(
            f"gcloud iam service-accounts create {AGENT_PLATFORM_SA_NAME} \
                --display-name=\"Agent Platform Service Account\" \
                --project={PROJECT_ID}",
            "Creating Agent Platform service account",
            check=True
        )
    
    # Grant permissions to Agent Platform SA
    agent_sa_email = f"{AGENT_PLATFORM_SA_NAME}@{PROJECT_ID}.iam.gserviceaccount.com"
    
    run_command(
        f'gcloud projects add-iam-policy-binding {PROJECT_ID} '
        f'--member="serviceAccount:{agent_sa_email}" '
        f'--role="roles/artifactregistry.reader"',
        "Granting Artifact Registry Reader to Agent Platform SA",
        check=False
    )
    
    run_command(
        f'gcloud projects add-iam-policy-binding {PROJECT_ID} '
        f'--member="serviceAccount:{agent_sa_email}" '
        f'--role="roles/secretmanager.secretAccessor"',
        "Granting Secret Manager Accessor to Agent Platform SA",
        check=False
    )

def step_6_setup_workload_identity():
    """Setup Workload Identity binding."""
    print("\n" + "="*70)
    print("STEP 6: Setting up Workload Identity")
    print("="*70)
    
    # Browser Manager
    browser_sa_email = f"{BROWSER_MANAGER_SA_NAME}@{PROJECT_ID}.iam.gserviceaccount.com"
    browser_k8s_sa = f"serviceAccount:{PROJECT_ID}.svc.id.goog[{NAMESPACE}/browser-manager]"
    
    run_command(
        f'gcloud iam service-accounts add-iam-policy-binding {browser_sa_email} '
        f'--role="roles/iam.workloadIdentityUser" '
        f'--member="{browser_k8s_sa}" '
        f'--project={PROJECT_ID}',
        "Binding Browser Manager K8s SA to GCP SA"
    )
    
    # Agent Platform
    agent_sa_email = f"{AGENT_PLATFORM_SA_NAME}@{PROJECT_ID}.iam.gserviceaccount.com"
    agent_k8s_sa = f"serviceAccount:{PROJECT_ID}.svc.id.goog[{NAMESPACE}/agent-platform]"
    
    run_command(
        f'gcloud iam service-accounts add-iam-policy-binding {agent_sa_email} '
        f'--role="roles/iam.workloadIdentityUser" '
        f'--member="{agent_k8s_sa}" '
        f'--project={PROJECT_ID}',
        "Binding Agent Platform K8s SA to GCP SA"
    )

def step_7_create_github_sa_key():
    """Create and download GitHub Actions SA key."""
    print("\n" + "="*70)
    print("STEP 7: Creating GitHub Actions Key")
    print("="*70)
    
    github_sa_email = f"{GITHUB_SA_NAME}@{PROJECT_ID}.iam.gserviceaccount.com"
    key_file = "github-sa-key.json"
    
    # Delete old keys
    run_command(
        f"gcloud iam service-accounts keys list \
            --iam-account={github_sa_email} \
            --filter='keyType:USER_MANAGED' \
            --format='value(name)' | \
            xargs -I {{}} gcloud iam service-accounts keys delete {{}} \
            --iam-account={github_sa_email} --quiet",
        "Deleting old GitHub Actions keys",
        check=False
    )
    
    # Create new key
    run_command(
        f"gcloud iam service-accounts keys create {key_file} \
            --iam-account={github_sa_email} \
            --project={PROJECT_ID}",
        f"Creating new key: {key_file}"
    )
    
    print(f"\n✅ Key saved to: {key_file}")
    return key_file

def step_8_push_github_secrets(key_file):
    """Push secrets to GitHub."""
    print("\n" + "="*70)
    print("STEP 8: Pushing Secrets to GitHub")
    print("="*70)
    
    # Read the service account key
    with open(key_file, 'r') as f:
        sa_key_content = f.read()
    
    # GitHub secrets to set
    secrets = {
        "GCP_PROJECT_ID": PROJECT_ID,
        "GCP_REGION": REGION,
        "GCP_REGISTRY": REGISTRY,
        "GKE_CLUSTER_NAME": CLUSTER_NAME,
        "GKE_ZONE": ZONE,
        "GCP_SA_KEY": sa_key_content,
    }
    
    for secret_name, secret_value in secrets.items():
        if secret_name == "GCP_SA_KEY":
            # Use file for large JSON
            run_command(
                f"gh secret set {secret_name} --repo {GITHUB_REPO} < {key_file}",
                f"Setting GitHub secret: {secret_name}"
            )
        else:
            # Use --body for simple strings
            run_command(
                f'gh secret set {secret_name} --repo {GITHUB_REPO} --body "{secret_value}"',
                f"Setting GitHub secret: {secret_name}"
            )
    
    print(f"\n✅ All secrets pushed to GitHub repo: {GITHUB_REPO}")

def step_9_apply_kubernetes_manifests():
    """Apply Kubernetes manifests."""
    print("\n" + "="*70)
    print("STEP 9: Applying Kubernetes Manifests")
    print("="*70)
    
    print("\n⚠️  NOTE: The GitHub Actions workflow contains the authoritative K8s manifests.")
    print("This step only applies standalone YAML files from k8s/ directory.")
    print("For production deployments, use: git push (triggers GitHub Actions)\n")
    
    # Apply namespace
    run_command(
        f"kubectl apply -f k8s/namespace.yaml",
        "Creating namespace",
        check=False
    )
    
    # Apply browser-manager RBAC
    run_command(
        f"kubectl apply -f k8s/browser-manager-rbac.yaml",
        "Creating RBAC for browser-manager",
        check=False
    )
    
    # Apply agent-platform RBAC
    run_command(
        f"kubectl apply -f k8s/agent-platform-rbac.yaml",
        "Creating RBAC for agent-platform",
        check=False
    )
    
    # Apply browser-manager secret
    run_command(
        f"kubectl apply -f k8s/browser-manager-secret.yaml",
        "Creating secrets for browser-manager",
        check=False
    )
    
    # Apply browser-manager deployment
    run_command(
        f"kubectl apply -f k8s/browser-manager-deployment.yaml",
        "Deploying browser-manager",
        check=False
    )
    
    # Apply agent-platform deployment
    run_command(
        f"kubectl apply -f k8s/agent-platform-deployment.yaml",
        "Deploying agent-platform",
        check=False
    )
    
    print("\n⏳ Waiting for deployments to be ready...")
    run_command(
        f"kubectl rollout status deployment/browser-manager -n {NAMESPACE} --timeout=5m",
        "Waiting for browser-manager deployment",
        check=False
    )
    
    run_command(
        f"kubectl rollout status deployment/agent-platform -n {NAMESPACE} --timeout=5m",
        "Waiting for agent-platform deployment",
        check=False
    )

def step_10_verify():
    """Verify everything works."""
    print("\n" + "="*70)
    print("STEP 10: Verification")
    print("="*70)
    
    # Check pods
    run_command(
        f"kubectl get pods -n {NAMESPACE}",
        "Checking pods",
        check=False
    )
    
    # Check services
    run_command(
        f"kubectl get services -n {NAMESPACE}",
        "Checking services",
        check=False
    )
    
    # Check deployments
    run_command(
        f"kubectl get deployments -n {NAMESPACE}",
        "Checking deployments",
        check=False
    )
    
    print("\n" + "="*70)
    print("🌐 Service URLs")
    print("="*70)
    print("\nTo get external IPs (LoadBalancer services):")
    print(f"  kubectl get svc -n {NAMESPACE}")
    print("\nTo access services locally:")
    print(f"  kubectl port-forward -n {NAMESPACE} svc/browser-manager 8000:8000")
    print(f"  kubectl port-forward -n {NAMESPACE} svc/agent-platform 5000:5000")

def cleanup_key_file(key_file):
    """Clean up temporary key file."""
    print("\n" + "="*70)
    print("CLEANUP")
    print("="*70)
    
    if confirm(f"Delete temporary key file '{key_file}'? (Recommended for security)"):
        Path(key_file).unlink(missing_ok=True)
        print(f"✅ Deleted {key_file}")
    else:
        print(f"⚠️  Key file kept: {key_file}")
        print(f"⚠️  Remember to delete it manually later!")

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("""
    ╔═══════════════════════════════════════════════════════════════╗
    ║                                                               ║
    ║   🚀 Doot Agent - Complete GKE Setup Automation              ║
    ║                                                               ║
    ║   This script will:                                           ║
    ║   • Create GKE cluster                                        ║
    ║   • Create service accounts (3 total)                         ║
    ║   • Setup Workload Identity (browser-manager + agent)         ║
    ║   • Create Kubernetes RBAC                                    ║
    ║   • Push secrets to GitHub                                    ║
    ║   • Deploy browser-manager + agent-platform                   ║
    ║                                                               ║
    ║   Note: Secrets for agent-platform (Redis, Postgres,         ║
    ║   Supabase) must be uploaded separately using:               ║
    ║   python upload-secrets.py                                    ║
    ║                                                               ║
    ╚═══════════════════════════════════════════════════════════════╝
    """)
    
    print(f"\n📋 Configuration:")
    print(f"   Project ID: {PROJECT_ID}")
    print(f"   Region: {REGION}")
    print(f"   Zone: {ZONE}")
    print(f"   Cluster: {CLUSTER_NAME}")
    print(f"   GitHub Repo: {GITHUB_REPO}")
    
    if not confirm("Continue with this configuration?"):
        print("\n👋 Aborted. Edit the script to change configuration.")
        sys.exit(0)
    
    try:
        step_1_check_prerequisites()
        step_1b_check_or_create_project()
        step_2_enable_apis()
        step_3_create_artifact_registry()
        step_4_create_gke_cluster()
        step_5_create_service_accounts()
        step_6_setup_workload_identity()
        key_file = step_7_create_github_sa_key()
        step_8_push_github_secrets(key_file)
        
        # MANUAL STEP: Update K8s manifests if you changed PROJECT_ID or naming
        print("\n" + "="*70)
        print("⚠️  MANUAL STEP REQUIRED")
        print("="*70)
        print("If you changed PROJECT_ID, REGION, or naming conventions above,")
        print("you MUST manually edit these files before proceeding:")
        print("  - k8s/namespace.yaml (namespace name)")
        print("  - k8s/browser-manager-rbac.yaml (namespace + service account email)")
        print("  - k8s/browser-manager-secret.yaml (image URLs + project ID)")
        print("  - k8s/browser-manager-deployment.yaml (image URL + namespace)")
        print("\nCurrent values:")
        print(f"  PROJECT_ID: {PROJECT_ID}")
        print(f"  NAMESPACE: {NAMESPACE}")
        print(f"  REGISTRY: {REGISTRY}")
        print(f"  Service Account: {BROWSER_MANAGER_SA_NAME}@{PROJECT_ID}.iam.gserviceaccount.com")
        
        if not confirm("Have you updated the K8s manifests (if needed)?"):
            print("\n👋 Stopping. Please update K8s manifests and run again.")
            sys.exit(0)
        
        step_9_apply_kubernetes_manifests()
        step_10_verify()
        
        print("\n" + "="*70)
        print("🎉 SUCCESS! GKE Infrastructure is set up!")
        print("="*70)
        print("\n✅ What was created:")
        print("   • GKE cluster: doot-cluster")
        print("   • 3 Service Accounts:")
        print("     - github-actions-sa (for CI/CD)")
        print("     - browser-manager-sa (Workload Identity)")
        print("     - agent-platform-sa (Workload Identity)")
        print("   • Artifact Registry: doot-agent-repo")
        print("   • GitHub secrets pushed")
        print("   • Kubernetes RBAC configured")
        print("\n✅ Next steps:")
        print("   1. Upload application secrets to GCP Secret Manager:")
        print("      python upload-secrets.py")
        print("   2. Push code to GitHub to trigger deployment:")
        print("      git push origin main")
        print("   3. Monitor deployment:")
        print("      https://github.com/Veer376/doot-agent/actions")
        print("   4. Get service URLs after deployment:")
        print(f"      kubectl get svc -n {NAMESPACE}")
        print("   5. Test services:")
        print(f"      kubectl port-forward -n {NAMESPACE} svc/agent-platform 5000:5000")
        print(f"      kubectl port-forward -n {NAMESPACE} svc/browser-manager 8000:8000")
        
        cleanup_key_file(key_file)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user. Some steps may be incomplete.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
