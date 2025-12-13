#!/usr/bin/env python3
"""
Step 10: Setup HTTPS with Google-Managed SSL
Creates static IP, Ingress, and Google-managed SSL certificate for HTTPS access.
"""

import sys
import subprocess
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from config import (
    PROJECT_ID,
    NAMESPACE,
    DOMAIN,
    STATIC_IP_NAME,
    CERT_NAME,
    ENABLE_HTTPS
)
from utils import run_command, confirm, print_header, print_success, print_warning, print_error

def run():
    """Setup HTTPS Ingress with Google-managed SSL."""
    if not ENABLE_HTTPS:
        print_warning("HTTPS setup disabled in config.py")
        return
    
    print_header("STEP 10: Setting up HTTPS with Google-Managed SSL")
    
    if DOMAIN == "api.yourdomain.com":
        print_error("You must set your DOMAIN in config.py!")
        print("Edit k8s-setup/config.py and set DOMAIN to your actual domain.")
        sys.exit(1)
    
    print(f"\n📋 Configuration:")
    print(f"   Domain: {DOMAIN}")
    print(f"   Static IP: {STATIC_IP_NAME}")
    print(f"   Certificate: {CERT_NAME}")
    
    if not confirm("Continue with HTTPS setup?"):
        print_warning("Skipping HTTPS setup")
        return
    
    # Step 1: Create static IP
    print("\n📌 Step 10.1: Creating static IP...")
    result = subprocess.run(
        f"gcloud compute addresses describe {STATIC_IP_NAME} --global --project={PROJECT_ID} --format='value(address)'",
        shell=True,
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        ip_address = result.stdout.strip()
        print_success(f"Static IP already exists: {ip_address}")
    else:
        run_command(
            f"gcloud compute addresses create {STATIC_IP_NAME} --global --project={PROJECT_ID}",
            "Creating global static IP",
            check=False  # Don't fail if already exists
        )
        
        result = subprocess.run(
            f"gcloud compute addresses describe {STATIC_IP_NAME} --global --project={PROJECT_ID} --format='value(address)'",
            shell=True,
            capture_output=True,
            text=True
        )
        ip_address = result.stdout.strip()
        print_success(f"Static IP created: {ip_address}")
    
    # Step 2: Create Ingress manifest
    print("\n📌 Step 10.2: Creating Ingress manifest...")
    manifests_dir = Path(__file__).parent.parent / "manifests"
    manifests_dir.mkdir(exist_ok=True)
    
    ingress_yaml = f"""apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: agent-platform-ingress
  namespace: {NAMESPACE}
  annotations:
    kubernetes.io/ingress.class: "gce"
    kubernetes.io/ingress.global-static-ip-name: "{STATIC_IP_NAME}"
    networking.gke.io/managed-certificates: "{CERT_NAME}"
    kubernetes.io/ingress.allow-http: "false"
spec:
  rules:
  - host: {DOMAIN}
    http:
      paths:
      - path: /*
        pathType: ImplementationSpecific
        backend:
          service:
            name: agent-platform
            port:
              number: 5000
---
apiVersion: networking.gke.io/v1
kind: ManagedCertificate
metadata:
  name: {CERT_NAME}
  namespace: {NAMESPACE}
spec:
  domains:
    - {DOMAIN}
"""
    
    ingress_file = manifests_dir / "ingress-https.yaml"
    with open(ingress_file, 'w') as f:
        f.write(ingress_yaml)
    
    print_success(f"Ingress manifest created: {ingress_file}")
    
    # Step 3: Apply Ingress
    print("\n📌 Step 10.3: Applying Ingress...")
    run_command(
        f"kubectl apply -f {ingress_file}",
        "Applying Ingress and ManagedCertificate"
    )
    
    # Step 4: Instructions
    print("\n" + "="*70)
    print("✅ HTTPS Setup Complete!")
    print("="*70)
    print(f"\n📋 Next Steps:")
    print(f"\n1. Point your domain DNS to the static IP:")
    print(f"   Domain: {DOMAIN}")
    print(f"   IP Address: {ip_address}")
    print(f"\n   Add an A record in your DNS provider:")
    print(f"   Type: A")
    print(f"   Name: {DOMAIN.split('.')[0] if DOMAIN.count('.') > 1 else '@'}")
    print(f"   Value: {ip_address}")
    print(f"   TTL: 300 (or default)")
    
    print(f"\n2. Wait for SSL certificate provisioning (10-15 minutes)")
    print(f"   Check status:")
    print(f"   kubectl describe managedcertificate {CERT_NAME} -n {NAMESPACE}")
    
    print(f"\n3. Once Status=Active, access your API at:")
    print(f"   https://{DOMAIN}")
    
    print(f"\n4. Update your frontend .env:")
    print(f"   NEXT_PUBLIC_API_URL=https://{DOMAIN}")
    
    print("\n" + "="*70)
    print("⚠️  IMPORTANT:")
    print("="*70)
    print("• DNS propagation can take up to 48 hours")
    print("• SSL certificate provisioning takes 10-15 minutes AFTER DNS is set")
    print("• The Ingress will show a backend error until certificate is active")
    print("• Test DNS: nslookup " + DOMAIN)
    print("• Test HTTPS: curl -v https://" + DOMAIN)

if __name__ == "__main__":
    run()
