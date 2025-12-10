"""Configuration for browser-manager service"""
import os
from pydantic import field_validator
from pydantic_settings import BaseSettings


class Config(BaseSettings):
    """Browser Manager configuration"""
    
    # Service
    host: str = "0.0.0.0"
    port: int = 8000
    
    @field_validator('port', mode='before')
    @classmethod
    def parse_port(cls, v):
        """Handle Kubernetes PORT env var which might be tcp://host:port format"""
        if isinstance(v, str):
            # If it's a Kubernetes service URL like tcp://10.0.0.1:8000, extract the port
            if v.startswith('tcp://'):
                v = v.split(':')[-1]
            return int(v)
        return v
    
    # Kubernetes
    namespace: str = "orbit-agent"
    browser_image: str = os.getenv("BROWSER_IMAGE", "gcr.io/orbit-agent/orbit-browser:latest")
    
    # Resource limits
    max_browsers: int = int(os.getenv("MAX_BROWSERS", "20"))
    browser_memory_request: str = "1Gi"
    browser_memory_limit: str = "2Gi"
    browser_cpu_request: str = "500m"
    browser_cpu_limit: str = "1000m"
    browser_shm_size: str = "1Gi"
    
    # Container lifecycle
    idle_timeout_seconds: int = 300  # 5 minutes
    max_lifetime_seconds: int = 3600  # 1 hour
    cleanup_interval_seconds: int = 60  # 1 minute
    
    # Browser ports
    cdp_port: int = 9223
    vnc_port: int = 6080
    
    # GCP
    gcp_project_id: str = os.getenv("GCP_PROJECT_ID", "orbit-agent")
    environment: str = os.getenv("ENVIRONMENT", "development")
    
    class Config:
        env_prefix = "BROWSER_MANAGER_"


config = Config()
