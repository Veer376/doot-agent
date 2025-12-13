#!/usr/bin/env python3
"""
Orbit Agent - Kubernetes Setup Orchestrator

Runs all setup steps in sequence to fully configure GKE infrastructure.

Usage:
    python run_all.py                    # Run all steps
    python run_all.py --skip-https       # Skip HTTPS setup
    python run_all.py --start-from 5     # Start from step 5
"""

import sys
import argparse
from pathlib import Path

# Add steps directory to path
steps_dir = Path(__file__).parent / "steps"
sys.path.insert(0, str(steps_dir))

# Import all steps
import step_00_prerequisites
import step_01_project_billing
import step_02_enable_apis
import step_03_artifact_registry
import step_04_gke_cluster
import step_05_service_accounts
import step_06_workload_identity
import step_07_github_secrets
import step_08_kubernetes_manifests
import step_09_verify
import step_10_https_ingress

from utils import print_header, print_success, confirm

STEPS = [
    ("00", "Prerequisites", step_00_prerequisites),
    ("01", "Project & Billing", step_01_project_billing),
    ("02", "Enable APIs", step_02_enable_apis),
    ("03", "Artifact Registry", step_03_artifact_registry),
    ("04", "GKE Cluster", step_04_gke_cluster),
    ("05", "Service Accounts", step_05_service_accounts),
    ("06", "Workload Identity", step_06_workload_identity),
    ("07", "GitHub Secrets", step_07_github_secrets),
    ("08", "Kubernetes Manifests", step_08_kubernetes_manifests),
    ("09", "Verification", step_09_verify),
    ("10", "HTTPS Ingress", step_10_https_ingress),
]

def main():
    parser = argparse.ArgumentParser(description="Run GKE setup steps")
    parser.add_argument("--start-from", type=int, default=0, help="Start from step number")
    parser.add_argument("--skip-https", action="store_true", help="Skip HTTPS setup (step 10)")
    args = parser.parse_args()
    
    print("""
    ╔═══════════════════════════════════════════════════════════════╗
    ║                                                               ║
    ║   🚀 Orbit Agent - GKE Setup with HTTPS                      ║
    ║                                                               ║
    ║   This will execute all setup steps:                          ║
    ║   • Create GKE cluster                                        ║
    ║   • Configure service accounts                                ║
    ║   • Setup Workload Identity                                   ║
    ║   • Deploy applications                                       ║
    ║   • Configure HTTPS with Google-managed SSL                   ║
    ║                                                               ║
    ╚═══════════════════════════════════════════════════════════════╝
    """)
    
    steps_to_run = STEPS[args.start_from:]
    
    if args.skip_https:
        steps_to_run = [s for s in steps_to_run if s[0] != "10"]
    
    print("\n📋 Steps to execute:")
    for step_num, step_name, _ in steps_to_run:
        print(f"   Step {step_num}: {step_name}")
    
    if not confirm("\nProceed with setup?"):
        print("\n👋 Setup cancelled")
        sys.exit(0)
    
    # Run steps
    for step_num, step_name, step_module in steps_to_run:
        try:
            print_header(f"Running Step {step_num}: {step_name}")
            step_module.run()
        except KeyboardInterrupt:
            print("\n\n⚠️  Setup interrupted by user")
            sys.exit(1)
        except Exception as e:
            print(f"\n\n❌ Step {step_num} failed: {e}")
            if not confirm("Continue with next step?"):
                sys.exit(1)
    
    print("\n" + "="*70)
    print("🎉 SETUP COMPLETE!")
    print("="*70)
    print("\n✅ Your GKE infrastructure is ready!")
    print("\nNext steps:")
    print("1. Upload application secrets:")
    print("   python upload-secrets.py")
    print("\n2. Deploy via GitHub Actions:")
    print("   git push origin main")
    print("\n3. Monitor deployment:")
    print("   kubectl get pods -n doot-agent -w")
    
    if not args.skip_https:
        print("\n4. Configure DNS for HTTPS (see step 10 output)")
    
    print("\n" + "="*70)

if __name__ == "__main__":
    main()
