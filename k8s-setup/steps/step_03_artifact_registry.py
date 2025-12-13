#!/usr/bin/env python3
"""
Step 03: Create Artifact Registry
Creates a Docker repository in Google Artifact Registry.
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from config import PROJECT_ID, REGION, REPOSITORY
from utils import run_command, print_header

def run():
    """Create Artifact Registry repository."""
    print_header("STEP 03: Creating Artifact Registry")
    
    run_command(
        f"gcloud artifacts repositories create {REPOSITORY} \
            --repository-format=docker \
            --location={REGION} \
            --project={PROJECT_ID}",
        "Creating Artifact Registry repository",
        check=False
    )

if __name__ == "__main__":
    run()
