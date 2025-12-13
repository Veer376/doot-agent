#!/usr/bin/env python3
"""
Step 07: Push Secrets to GitHub
Creates service account key and uploads all secrets to GitHub repository.
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from config import (
    PROJECT_ID,
    REGION,
    REGISTRY,
    CLUSTER_NAME,
    ZONE,
    GITHUB_SA_NAME,
    GITHUB_REPO
)
from utils import run_command, confirm, print_header, print_success

def run():
    """Push secrets to GitHub."""
    print_header("STEP 07: Pushing Secrets to GitHub")
    
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
        f"Creating service account key"
    )
    
    # Read key
    with open(key_file, 'r') as f:
        sa_key_content = f.read()
    
    # GitHub secrets
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
            run_command(
                f"gh secret set {secret_name} --repo {GITHUB_REPO} < {key_file}",
                f"Setting {secret_name}"
            )
        else:
            run_command(
                f'gh secret set {secret_name} --repo {GITHUB_REPO} --body "{secret_value}"',
                f"Setting {secret_name}"
            )
    
    # Cleanup
    if confirm(f"Delete temporary key file '{key_file}'?"):
        Path(key_file).unlink(missing_ok=True)
        print_success(f"Deleted {key_file}")
    
    print_success("All secrets pushed to GitHub")

if __name__ == "__main__":
    run()
