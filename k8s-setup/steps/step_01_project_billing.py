#!/usr/bin/env python3
"""
Step 01: Check/Create GCP Project & Enable Billing
Ensures the GCP project exists and has billing enabled.
"""

import sys
import subprocess
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from config import PROJECT_ID
from utils import run_command, confirm, print_header, print_success, print_error, print_warning

def run():
    """Check or create GCP project and enable billing."""
    print_header("STEP 01: Checking GCP Project & Billing")
    
    # Check if project exists and is active
    result = subprocess.run(
        f"gcloud projects describe {PROJECT_ID} --format='value(lifecycleState)'",
        shell=True,
        capture_output=True,
        text=True
    )
    
    lifecycle_state = result.stdout.strip() if result.returncode == 0 else None
    
    if result.returncode == 0 and lifecycle_state == "ACTIVE":
        print_success(f"Project '{PROJECT_ID}' exists and is active")
        
        # Check billing
        print("\n📌 Checking billing status...")
        billing_result = subprocess.run(
            f"gcloud beta billing projects describe {PROJECT_ID} --format='value(billingAccountName)'",
            shell=True,
            capture_output=True,
            text=True
        )
        
        if billing_result.returncode == 0 and billing_result.stdout.strip():
            billing_account = billing_result.stdout.strip().split('/')[-1]
            print_success(f"Billing enabled: {billing_account}")
            return
        else:
            print_warning("Project exists but billing is NOT enabled!")
            print_error("GCP requires billing to be enabled for GKE, Artifact Registry, etc.")
            
            if not confirm("Link billing account now?"):
                print_error("Billing required. Enable manually at:")
                print(f"https://console.cloud.google.com/billing/linkedaccount?project={PROJECT_ID}")
                sys.exit(1)
            
            _link_billing()
            return
    
    # Project doesn't exist
    print_warning(f"Project '{PROJECT_ID}' not found")
    
    if not confirm(f"Create project '{PROJECT_ID}'?"):
        print_error("Project required. Create manually or update PROJECT_ID in config.py")
        sys.exit(1)
    
    # Create project
    run_command(
        f"gcloud projects create {PROJECT_ID} --name='{PROJECT_ID}'",
        f"Creating project '{PROJECT_ID}'"
    )
    
    print_success(f"Project '{PROJECT_ID}' created")
    _link_billing()

def _link_billing():
    """Link billing account to project."""
    print("\n📌 Linking billing account...")
    print("\n📋 Available billing accounts:")
    print("-" * 70)
    subprocess.run("gcloud beta billing accounts list", shell=True)
    print("-" * 70)
    
    billing_account = input("\n🤔 Enter billing account ID (format: XXXXXX-XXXXXX-XXXXXX): ").strip()
    
    if not billing_account:
        print_error("Billing account ID required")
        sys.exit(1)
    
    result = subprocess.run(
        f"gcloud beta billing projects link {PROJECT_ID} --billing-account={billing_account}",
        shell=True,
        check=False
    )
    
    if result.returncode != 0:
        print_error("Billing link failed. Link manually at:")
        print(f"https://console.cloud.google.com/billing/linkedaccount?project={PROJECT_ID}")
        sys.exit(1)
    
    print_success(f"Billing linked to project '{PROJECT_ID}'")

if __name__ == "__main__":
    run()
