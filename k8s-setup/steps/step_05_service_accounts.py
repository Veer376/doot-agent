#!/usr/bin/env python3
"""
Step 05: Create GCP Service Accounts
Creates service accounts for GitHub Actions, Browser Manager, and Agent Platform.
"""

import sys
import subprocess
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from config import (
    PROJECT_ID,
    GITHUB_SA_NAME,
    BROWSER_MANAGER_SA_NAME,
    AGENT_PLATFORM_SA_NAME
)
from utils import run_command, print_header, print_success

def run():
    """Create GCP service accounts."""
    print_header("STEP 05: Creating Service Accounts")
    
    # 1. GitHub Actions SA
    _create_sa_if_not_exists(
        GITHUB_SA_NAME,
        "GitHub Actions Service Account",
        [
            "roles/artifactregistry.writer",
            "roles/container.admin",
            "roles/iam.serviceAccountUser",
        ]
    )
    
    # 2. Browser Manager SA
    _create_sa_if_not_exists(
        BROWSER_MANAGER_SA_NAME,
        "Browser Manager Service Account",
        [
            "roles/artifactregistry.reader",
            "roles/secretmanager.secretAccessor",
        ]
    )
    
    # 3. Agent Platform SA
    _create_sa_if_not_exists(
        AGENT_PLATFORM_SA_NAME,
        "Agent Platform Service Account",
        [
            "roles/artifactregistry.reader",
            "roles/secretmanager.secretAccessor",
        ]
    )
    
    print_success("All service accounts created")

def _create_sa_if_not_exists(sa_name, display_name, roles):
    """Create service account if it doesn't exist and grant roles."""
    sa_email = f"{sa_name}@{PROJECT_ID}.iam.gserviceaccount.com"
    
    result = subprocess.run(
        f"gcloud iam service-accounts describe {sa_email} --project={PROJECT_ID}",
        shell=True,
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print_success(f"{display_name} already exists")
    else:
        run_command(
            f'gcloud iam service-accounts create {sa_name} \
                --display-name="{display_name}" \
                --project={PROJECT_ID}',
            f"Creating {display_name}"
        )
    
    # Grant roles
    for role in roles:
        run_command(
            f'gcloud projects add-iam-policy-binding {PROJECT_ID} \
                --member="serviceAccount:{sa_email}" \
                --role="{role}"',
            f"Granting {role} to {sa_name}",
            check=False
        )

if __name__ == "__main__":
    run()
