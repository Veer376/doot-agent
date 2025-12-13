#!/usr/bin/env python3
"""
Step 00: Check Prerequisites
Verifies that all required tools are installed and authenticated.
"""

import sys
import subprocess
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from utils import check_prerequisite, print_header, print_success, print_error

def run():
    """Check all prerequisites."""
    print_header("STEP 00: Checking Prerequisites")
    
    prerequisites = [
        ("gcloud", "Google Cloud SDK"),
        ("kubectl", "Kubernetes CLI"),
        ("gh", "GitHub CLI"),
        ("docker", "Docker"),
    ]
    
    all_good = True
    for cmd, name in prerequisites:
        if not check_prerequisite(cmd, name):
            all_good = False
    
    if not all_good:
        print_error("Missing prerequisites. Please install them first.")
        sys.exit(1)
    
    # Check gcloud auth
    result = subprocess.run(
        "gcloud config get-value account",
        shell=True,
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0 and result.stdout.strip() and result.stdout.strip() != "(unset)":
        print_success(f"Authenticated to GCP as: {result.stdout.strip()}")
    else:
        print_error("Not authenticated to GCP. Run: gcloud auth login")
        sys.exit(1)
    
    # Check gh auth
    result = subprocess.run(
        "gh auth status",
        shell=True,
        check=False,
        capture_output=True
    )
    
    if result.returncode != 0:
        print_error("Not authenticated to GitHub. Run: gh auth login")
        sys.exit(1)
    
    print_success("Authenticated to GitHub")
    print_success("All prerequisites met!")

if __name__ == "__main__":
    run()
