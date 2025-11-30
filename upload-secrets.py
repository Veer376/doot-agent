#!/usr/bin/env python3
"""
Bulk upload secrets from .env file to Google Cloud Secret Manager
Grants access to both GitHub Actions and Cloud Run service accounts
"""
import os
import subprocess
import sys

def run_command(cmd, input_data=None, capture_output=True):
    """Run a shell command and return success status and output"""
    try:
        if input_data:
            result = subprocess.run(
                cmd,
                shell=True,
                input=input_data,
                check=True,
                capture_output=capture_output,
                text=True
            )
        else:
            result = subprocess.run(
                cmd, 
                shell=True, 
                check=True, 
                capture_output=capture_output,
                text=True
            )
        return True, result.stdout if capture_output else ""
    except subprocess.CalledProcessError as e:
        return False, e.stderr if capture_output else ""

def get_project_number(project_id):
    """Get GCP project number from project ID"""
    cmd = f'gcloud projects describe {project_id} --format="value(projectNumber)"'
    success, output = run_command(cmd)
    if success:
        return output.strip()
    return None

def main():
    # Check for .env file
    if not os.path.exists('.env'):
        print("❌ Error: .env file not found!")
        sys.exit(1)
    
    # Get project configuration
    project_id = os.environ.get('PROJECT_ID', 'orbit-agent')
    github_sa = os.environ.get('SA_EMAIL', f'github-actions-sa@{project_id}.iam.gserviceaccount.com')
    
    print(f"🔐 Bulk Secret Upload to Google Cloud Secret Manager")
    print(f"Project: {project_id}\n")
    
    # Get project number for compute service account
    print("Getting project number...")
    project_number = get_project_number(project_id)
    if not project_number:
        print("⚠️  Warning: Could not get project number. Cloud Run permissions may need manual setup.")
        cloudrun_sa = None
    else:
        cloudrun_sa = f"{project_number}-compute@developer.gserviceaccount.com"
        print(f"Cloud Run SA: {cloudrun_sa}\n")
    
    stats = {'success': 0, 'skip': 0, 'fail': 0}
    secrets_created = []
    
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
            exists, _ = run_command(check_cmd)
            
            if exists:
                print("exists (adding new version)... ", end='', flush=True)
                # Add new version
                cmd = f'gcloud secrets versions add {key} --data-file=- --project={project_id}'
            else:
                # Create new secret
                cmd = f'gcloud secrets create {key} --data-file=- --project={project_id}'
            
            # Upload secret
            success, error = run_command(cmd, value)
            if success:
                print("✓")
                stats['success'] += 1
                secrets_created.append(key)
            else:
                print(f"✗ failed: {error}")
                stats['fail'] += 1
    
    print(f"\n✅ Summary:")
    print(f"  Created/Updated: {stats['success']}")
    print(f"  Skipped: {stats['skip']}")
    print(f"  Failed: {stats['fail']}")
    
    # Grant IAM permissions to service accounts
    if stats['success'] > 0 and len(secrets_created) > 0:
        print(f"\n📝 Granting service account access to secrets...")
        
        service_accounts = []
        if github_sa:
            service_accounts.append(("GitHub Actions", github_sa))
        if cloudrun_sa:
            service_accounts.append(("Cloud Run", cloudrun_sa))
        
        if not service_accounts:
            print("⚠️  Warning: No service accounts configured. Skipping IAM binding.")
        else:
            for sa_name, sa_email in service_accounts:
                print(f"\n  Granting access to {sa_name} SA ({sa_email})...")
                success_count = 0
                
                for secret in secrets_created:
                    grant_cmd = (
                        f'gcloud secrets add-iam-policy-binding {secret} '
                        f'--member="serviceAccount:{sa_email}" '
                        f'--role="roles/secretmanager.secretAccessor" '
                        f'--project={project_id}'
                    )
                    success, _ = run_command(grant_cmd)
                    if success:
                        success_count += 1
                    else:
                        print(f"    ⚠️  Failed to grant access to {secret}")
                
                print(f"    ✓ Granted access to {success_count}/{len(secrets_created)} secrets")
    
    print("\n🎉 Done!")
    
    # Print verification commands
    print("\n📋 Verification Commands:")
    print(f"  List all secrets:")
    print(f"    gcloud secrets list --project={project_id}")
    print(f"\n  Check secret permissions:")
    print(f"    gcloud secrets get-iam-policy SECRET_NAME --project={project_id}")

if __name__ == '__main__':
    main()
