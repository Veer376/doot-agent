#!/usr/bin/env python3
"""
Step 04: Create GKE Cluster
Creates a Google Kubernetes Engine cluster with Workload Identity enabled.
"""

import sys
import subprocess
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from config import PROJECT_ID, ZONE, CLUSTER_NAME
from utils import run_command, confirm, print_header, print_success

def run():
    """Create GKE cluster."""
    print_header("STEP 04: Creating GKE Cluster")
    
    # Check if cluster exists
    check_result = subprocess.run(
        f"gcloud container clusters describe {CLUSTER_NAME} --zone={ZONE} --project={PROJECT_ID}",
        shell=True,
        capture_output=True,
        text=True
    )
    
    if check_result.returncode == 0:
        print_success(f"Cluster '{CLUSTER_NAME}' already exists")
        
        # Configure kubectl
        run_command(
            f"gcloud container clusters get-credentials {CLUSTER_NAME} \
                --zone={ZONE} \
                --project={PROJECT_ID}",
            "Configuring kubectl"
        )
        return
    
    if not confirm(f"Create GKE cluster '{CLUSTER_NAME}'? (Takes ~5 minutes, costs money)"):
        print("⏭️  Skipping cluster creation")
        return
    
    run_command(
        f"gcloud container clusters create {CLUSTER_NAME} \
            --zone={ZONE} \
            --project={PROJECT_ID} \
            --num-nodes=1 \
            --machine-type=e2-medium \
            --disk-size=20 \
            --enable-autoscaling \
            --min-nodes=1 \
            --max-nodes=5 \
            --enable-autorepair \
            --enable-autoupgrade \
            --workload-pool={PROJECT_ID}.svc.id.goog",
        "Creating GKE cluster (~5 minutes)"
    )
    
    # Configure kubectl
    run_command(
        f"gcloud container clusters get-credentials {CLUSTER_NAME} \
            --zone={ZONE} \
            --project={PROJECT_ID}",
        "Configuring kubectl"
    )

if __name__ == "__main__":
    run()
