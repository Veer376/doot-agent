#!/usr/bin/env python3
"""
Configuration file for GKE setup.
Edit these values before running the setup.
"""

# ============================================================================
# GCP CONFIGURATION
# ============================================================================

PROJECT_ID = "doot-agent"
REGION = "us-central1"
ZONE = "us-central1-a"
CLUSTER_NAME = "doot-cluster"
NAMESPACE = "doot-agent"

# ============================================================================
# SERVICE ACCOUNTS
# ============================================================================

GITHUB_SA_NAME = "github-actions-sa"
BROWSER_MANAGER_SA_NAME = "browser-manager-sa"
AGENT_PLATFORM_SA_NAME = "agent-platform-sa"

# ============================================================================
# GITHUB
# ============================================================================

GITHUB_REPO = "Veer376/doot-agent"

# ============================================================================
# REGISTRY
# ============================================================================

REGISTRY = f"{REGION}-docker.pkg.dev"
REPOSITORY = "doot-agent-repo"

# ============================================================================
# HTTPS/DOMAIN CONFIGURATION
# ============================================================================

# Set your domain for HTTPS access
# Example: "api.yourdomain.com"
DOMAIN = "api.dootagent.com"  # ⚠️ Backend API subdomain

# Static IP name for the Ingress
STATIC_IP_NAME = "agent-platform-ip"

# Managed certificate name
CERT_NAME = "agent-platform-cert"

# Enable HTTPS setup
ENABLE_HTTPS = True  # Set to False to skip HTTPS setup
