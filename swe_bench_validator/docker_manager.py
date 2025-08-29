"""
Docker client management with caching.
"""

import threading
from typing import Optional
import docker
from .utils import console

class DockerManager:
    """Singleton Docker client manager with lazy initialization."""
    
    _instance: Optional['DockerManager'] = None
    _lock = threading.Lock()
    
    def __new__(cls) -> 'DockerManager':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._client = None
                    cls._instance._initialized = False
        return cls._instance
    
    @property
    def client(self) -> docker.DockerClient:
        """Get Docker client with lazy initialization."""
        if not self._initialized:
            with self._lock:
                if not self._initialized:
                    self._initialize_client()
                    self._initialized = True
        return self._client
    
    def _initialize_client(self) -> None:
        """Initialize Docker client."""
        try:
            self._client = docker.from_env()
            # Test connection
            self._client.ping()
            console.print("✅ Docker client initialized successfully")
        except ImportError:
            raise ImportError("Docker library not installed. Install with: pip install docker")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Docker client: {str(e)}")
    
    def cleanup(self) -> None:
        """Cleanup Docker client."""
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass  # Ignore cleanup errors
        self._client = None
        self._initialized = False

# Global instance
docker_manager = DockerManager()
