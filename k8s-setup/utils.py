#!/usr/bin/env python3
"""
Utility functions for GKE setup scripts.
"""

import subprocess
import sys
import shutil

def run_command(cmd, description, check=True, capture_output=False):
    """Run shell command with pretty output."""
    print(f"\n{'='*70}")
    print(f"📌 {description}")
    print(f"{'='*70}")
    print(f"$ {cmd}\n")
    
    result = subprocess.run(
        cmd,
        shell=True,
        check=False,
        capture_output=capture_output,
        text=True
    )
    
    if result.returncode != 0:
        if check:
            print(f"❌ Failed: {description}")
            print(f"Error: {result.stderr if capture_output else 'See output above'}")
            sys.exit(1)
        else:
            print(f"⚠️  Warning: {description} (continuing anyway)")
            return None
    else:
        print(f"✅ Success: {description}")
        return result.stdout if capture_output else None

def check_prerequisite(cmd, name):
    """Check if a command exists."""
    path = shutil.which(cmd)
    if path:
        print(f"✅ {name} found at: {path}")
        return True

    try:
        result = subprocess.run(
            f"{cmd} --version",
            shell=True,
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        result = None

    if result and result.returncode == 0:
        out = (result.stdout or result.stderr or "").splitlines()
        ver = out[0] if out else "(version info)"
        print(f"✅ {name} available: {ver}")
        return True

    print(f"❌ {name} not found. Please install it first.")
    return False

def confirm(message):
    """Ask user for confirmation."""
    response = input(f"\n🤔 {message} (y/n): ").strip().lower()
    return response == 'y'

def print_header(title):
    """Print a formatted header."""
    print("\n" + "="*70)
    print(f"{title}")
    print("="*70)

def print_success(message):
    """Print a success message."""
    print(f"✅ {message}")

def print_error(message):
    """Print an error message."""
    print(f"❌ {message}")

def print_warning(message):
    """Print a warning message."""
    print(f"⚠️  {message}")
