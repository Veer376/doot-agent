"""Kubernetes Pod Manager - manages browser pods using K8s API"""
from kubernetes import client, config as k8s_config
from kubernetes.client.rest import ApiException
import time
from datetime import datetime
from typing import Optional


class KubernetesPodManager:
    """Manages browser pods using Kubernetes API"""
    
    def __init__(self, app_config):
        self.config = app_config
        self.namespace = app_config.namespace
        
        # Load K8s config (in-cluster when running in K8s)
        try:
            k8s_config.load_incluster_config()
            print("✓ Loaded in-cluster Kubernetes config")
        except k8s_config.ConfigException:
            # Fallback to local kubeconfig for development
            k8s_config.load_kube_config()
            print("✓ Loaded local Kubernetes config")
        
        self.core_api = client.CoreV1Api()
    
    def create_browser_pod(self, session_id: str, user_id: str) -> dict:
        """
        Create a browser pod for the user session.
        Returns pod info with service URLs.
        """
        pod_name = f"browser-{session_id}"
        
        # Define pod spec
        pod_manifest = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": pod_name,
                "namespace": self.namespace,
                "labels": {
                    "app": "orbit-browser",
                    "session-id": session_id,
                    "user-id": user_id,
                    "managed-by": "browser-manager",
                },
                "annotations": {
                    "created-at": datetime.utcnow().isoformat(),
                }
            },
            "spec": {
                "restartPolicy": "Never",  # Don't auto-restart
                "containers": [
                    {
                        "name": "browser",
                        "image": self.config.browser_image,
                        "imagePullPolicy": "Always",
                        "ports": [
                            {
                                "name": "cdp",
                                "containerPort": self.config.cdp_port,
                                "protocol": "TCP"
                            },
                            {
                                "name": "vnc",
                                "containerPort": self.config.vnc_port,
                                "protocol": "TCP"
                            }
                        ],
                        "env": [
                            {
                                "name": "DISPLAY",
                                "value": ":0"
                            },
                            {
                                "name": "SESSION_ID",
                                "value": session_id
                            },
                            {
                                "name": "USER_ID",
                                "value": user_id
                            }
                        ],
                        "resources": {
                            "requests": {
                                "memory": self.config.browser_memory_request,
                                "cpu": self.config.browser_cpu_request
                            },
                            "limits": {
                                "memory": self.config.browser_memory_limit,
                                "cpu": self.config.browser_cpu_limit
                            }
                        },
                        # Shared memory for Chromium
                        "volumeMounts": [
                            {
                                "name": "dshm",
                                "mountPath": "/dev/shm"
                            }
                        ]
                    }
                ],
                "volumes": [
                    {
                        "name": "dshm",
                        "emptyDir": {
                            "medium": "Memory",
                            "sizeLimit": self.config.browser_shm_size
                        }
                    }
                ]
            }
        }
        
        try:
            # Create pod
            pod = self.core_api.create_namespaced_pod(
                namespace=self.namespace,
                body=pod_manifest
            )
            
            print(f"✓ Created pod: {pod_name}")
            
            # Wait for pod to be running
            self._wait_for_pod_ready(pod_name)
            
            # Get pod IP
            pod = self.core_api.read_namespaced_pod(
                name=pod_name,
                namespace=self.namespace
            )
            pod_ip = pod.status.pod_ip
            
            return {
                "pod_name": pod_name,
                "pod_ip": pod_ip,
                "cdp_url": f"http://{pod_ip}:{self.config.cdp_port}",
                "vnc_url": f"http://{pod_ip}:{self.config.vnc_port}",
                "status": "running",
            }
        
        except ApiException as e:
            raise Exception(f"Failed to create pod: {e.reason}")
    
    def _wait_for_pod_ready(self, pod_name: str, timeout: int = 60):
        """Wait for pod to be in Running state"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                pod = self.core_api.read_namespaced_pod(
                    name=pod_name,
                    namespace=self.namespace
                )
                
                if pod.status.phase == "Running":
                    # Check if all containers are ready
                    if pod.status.container_statuses:
                        all_ready = all(
                            status.ready 
                            for status in pod.status.container_statuses
                        )
                        if all_ready:
                            print(f"✓ Pod {pod_name} is ready")
                            return True
                
                elif pod.status.phase in ["Failed", "Unknown"]:
                    raise Exception(f"Pod failed to start: {pod.status.phase}")
                
            except ApiException as e:
                if e.status != 404:
                    raise
            
            time.sleep(1)
        
        raise TimeoutError(f"Pod {pod_name} not ready after {timeout}s")
    
    def delete_pod(self, pod_name: str):
        """Delete a browser pod"""
        try:
            self.core_api.delete_namespaced_pod(
                name=pod_name,
                namespace=self.namespace,
                grace_period_seconds=5,
                propagation_policy="Foreground"
            )
            print(f"✓ Deleted pod: {pod_name}")
        except ApiException as e:
            if e.status != 404:  # Ignore if already deleted
                print(f"⚠️ Error deleting pod {pod_name}: {e.reason}")
    
    def list_browser_pods(self) -> list:
        """List all browser pods managed by browser-manager"""
        try:
            pods = self.core_api.list_namespaced_pod(
                namespace=self.namespace,
                label_selector="managed-by=browser-manager"
            )
            return pods.items
        except ApiException as e:
            print(f"⚠️ Error listing pods: {e.reason}")
            return []
    
    def cleanup_stale_pods(self, max_age_seconds: int):
        """Delete pods older than max_age_seconds"""
        pods = self.list_browser_pods()
        now = datetime.utcnow()
        
        for pod in pods:
            created_at_str = pod.metadata.annotations.get("created-at")
            if not created_at_str:
                continue
            
            try:
                created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                age = (now - created_at.replace(tzinfo=None)).seconds
                
                if age > max_age_seconds:
                    print(f"🧹 Cleaning up stale pod: {pod.metadata.name} (age: {age}s)")
                    self.delete_pod(pod.metadata.name)
            except (ValueError, AttributeError) as e:
                print(f"⚠️ Error parsing created-at for pod {pod.metadata.name}: {e}")
    
    def get_pod_status(self, pod_name: str) -> Optional[str]:
        """Get current pod status"""
        try:
            pod = self.core_api.read_namespaced_pod(
                name=pod_name,
                namespace=self.namespace
            )
            return pod.status.phase
        except ApiException:
            return None
    
    def get_pod_logs(self, pod_name: str, tail_lines: int = 50) -> str:
        """Get pod logs (useful for debugging)"""
        try:
            logs = self.core_api.read_namespaced_pod_log(
                name=pod_name,
                namespace=self.namespace,
                tail_lines=tail_lines
            )
            return logs
        except ApiException as e:
            return f"Error fetching logs: {e.reason}"
