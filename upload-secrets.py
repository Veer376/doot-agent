#!/usr/bin/env python3
"""
Bulk upload secrets from .env file to Google Cloud Secret Manager
"""
import os
import subprocess
import sys

def run_command(cmd, input_data=None):
    """Run a shell command and return success status"""
    try:
        if input_data:
            subprocess.run(
                cmd,
                shell=True,
                input=input_data.encode(),
                check=True,
                capture_output=True
            )
        else:
            subprocess.run(cmd, shell=True, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False

def main():
    # Check for .env file
    if not os.path.exists('.env'):
        print("❌ Error: .env file not found!")
        sys.exit(1)
    
    # Get project ID
    project_id = os.environ.get('PROJECT_ID', 'orbit-agent')
    sa_email = os.environ.get('SA_EMAIL', f'github-actions-sa@{project_id}.iam.gserviceaccount.com')
    
    print(f"🔐 Bulk Secret Upload to Google Cloud Secret Manager")
    print(f"Project: {project_id}\n")
    
    stats = {'success': 0, 'skip': 0, 'fail': 0}
    
    # Read .env file
    with open('.env', 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue
            
            # Parse key=value
            if '=' not in line:
                continue
            
            key, _, value = line.partition('=')
            key = key.strip()
            value = value.strip()
            
            # Remove quotes if present
            value = value.strip('"\'')
            
            # Skip if empty value
            if not value:
                print(f"⚠️  Skipping {key} (empty value)")
                stats['skip'] += 1
                continue
            
            print(f"Creating secret: {key}... ", end='', flush=True)
            
            # Check if secret exists
            check_cmd = f'gcloud secrets describe {key} --project={project_id}'
            exists = run_command(check_cmd)
            
            if exists:
                print("exists (adding new version)... ", end='', flush=True)
                # Add new version
                cmd = f'gcloud secrets versions add {key} --data-file=- --project={project_id}'
            else:
                # Create new secret
                cmd = f'gcloud secrets create {key} --data-file=- --project={project_id}'
            
            # Upload secret
            if run_command(cmd, value):
                print("✓")
                stats['success'] += 1
                
                # Grant service account access if it's a new secret
                if not exists:
                    grant_cmd = (
                        f'gcloud secrets add-iam-policy-binding {key} '
                        f'--member="serviceAccount:{sa_email}" '
                        f'--role="roles/secretmanager.secretAccessor" '
                        f'--project={project_id}'
                    )
                    run_command(grant_cmd)
            else:
                print("✗ failed")
                stats['fail'] += 1
    
    print(f"\n✅ Summary:")
    print(f"  Created/Updated: {stats['success']}")
    print(f"  Skipped: {stats['skip']}")
    print(f"  Failed: {stats['fail']}")
    print("\n🎉 Done!")

if __name__ == '__main__':
    main()
