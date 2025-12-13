#!/usr/bin/env python3
"""
Step 09: Verify Deployment
Checks that all resources are running correctly.
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from config import NAMESPACE
from utils import run_command, print_header, print_success

def run():
    """Verify deployment."""
    print_header("STEP 09: Verification")
    
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
    print("🌐 Access Services")
    print("="*70)
    print(f"\nGet service IPs:")
    print(f"  kubectl get svc -n {NAMESPACE}\n")
    print(f"Port forward locally:")
    print(f"  kubectl port-forward -n {NAMESPACE} svc/browser-manager 8000:8000")
    print(f"  kubectl port-forward -n {NAMESPACE} svc/agent-platform 5000:5000")
    
    print_success("Verification complete")

if __name__ == "__main__":
    run()
