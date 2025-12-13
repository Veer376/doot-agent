#!/usr/bin/env python3
"""
Step 02: Enable Required GCP APIs
Enables all necessary Google Cloud APIs for the project.
"""

import sys
import time
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from config import PROJECT_ID
from utils import run_command, print_header, print_success

def run():
    """Enable required GCP APIs."""
    print_header("STEP 02: Enabling GCP APIs")
    
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
            check=False
        )
    
    print("\n⏳ Waiting 30 seconds for APIs to propagate...")
    time.sleep(30)
    print_success("All APIs enabled")

if __name__ == "__main__":
    run()
