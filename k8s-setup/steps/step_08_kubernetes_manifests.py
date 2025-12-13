#!/usr/bin/env python3
"""
Step 08: Apply Kubernetes Manifests
Applies namespace, RBAC, secrets, and deployments to the cluster.
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from config import NAMESPACE
from utils import run_command, print_header, print_success

def run():
    """Apply Kubernetes manifests."""
    print_header("STEP 08: Applying Kubernetes Manifests")
    
    k8s_dir = Path(__file__).parent.parent.parent / "k8s"
    
    # Apply in order
    manifests = [
        "namespace.yaml",
        "browser-manager-rbac.yaml",
        "agent-platform-rbac.yaml",
        "browser-manager-secret.yaml",
        "browser-manager-deployment.yaml",
        "agent-platform-deployment.yaml",
    ]
    
    for manifest in manifests:
        manifest_path = k8s_dir / manifest
        if manifest_path.exists():
            run_command(
                f"kubectl apply -f {manifest_path}",
                f"Applying {manifest}",
                check=False
            )
    
    print("\n⏳ Waiting for deployments...")
    run_command(
        f"kubectl rollout status deployment/browser-manager -n {NAMESPACE} --timeout=5m",
        "Waiting for browser-manager",
        check=False
    )
    
    run_command(
        f"kubectl rollout status deployment/agent-platform -n {NAMESPACE} --timeout=5m",
        "Waiting for agent-platform",
        check=False
    )
    
    print_success("All manifests applied")

if __name__ == "__main__":
    run()
