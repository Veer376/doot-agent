#!/usr/bin/env python3
"""
Step 06: Setup Workload Identity
Binds Kubernetes service accounts to GCP service accounts.
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from config import (
    PROJECT_ID,
    NAMESPACE,
    BROWSER_MANAGER_SA_NAME,
    AGENT_PLATFORM_SA_NAME
)
from utils import run_command, print_header, print_success

def run():
    """Setup Workload Identity bindings."""
    print_header("STEP 06: Setting up Workload Identity")
    
    # Browser Manager
    browser_sa_email = f"{BROWSER_MANAGER_SA_NAME}@{PROJECT_ID}.iam.gserviceaccount.com"
    browser_k8s_sa = f"serviceAccount:{PROJECT_ID}.svc.id.goog[{NAMESPACE}/browser-manager]"
    
    run_command(
        f'gcloud iam service-accounts add-iam-policy-binding {browser_sa_email} \
            --role="roles/iam.workloadIdentityUser" \
            --member="{browser_k8s_sa}" \
            --project={PROJECT_ID}',
        "Binding Browser Manager K8s SA to GCP SA"
    )
    
    # Agent Platform
    agent_sa_email = f"{AGENT_PLATFORM_SA_NAME}@{PROJECT_ID}.iam.gserviceaccount.com"
    agent_k8s_sa = f"serviceAccount:{PROJECT_ID}.svc.id.goog[{NAMESPACE}/agent-platform]"
    
    run_command(
        f'gcloud iam service-accounts add-iam-policy-binding {agent_sa_email} \
            --role="roles/iam.workloadIdentityUser" \
            --member="{agent_k8s_sa}" \
            --project={PROJECT_ID}',
        "Binding Agent Platform K8s SA to GCP SA"
    )
    
    print_success("Workload Identity configured")

if __name__ == "__main__":
    run()
