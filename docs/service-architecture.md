# Service Architecture Documentation

## Overview

The FHR system has evolved from a single-file CLI tool to a modern containerized service with web interface. This document outlines the service architecture patterns, deployment strategies, and operational considerations for enterprise-grade deployments.

## Current Architecture Stack

### Application Layers

```mermaid
graph TB
    subgraph "Presentation Layer"
        Web[Static Web UI]
        Mobile[Mobile Interface]
        CLI[Command Line Interface]
    end
    
    subgraph "API Gateway Layer"
        Gateway[API Gateway/Load Balancer]
        Auth[Authentication Service]
        RateLimit[Rate Limiting]
    end
    
    subgraph "Application Layer"
        FastAPI[FastAPI Application]
        Background[Background Tasks]
        Scheduler[Task Scheduler]
    end
    
    subgraph "Business Logic Layer"
        Analyzer[AttendanceAnalyzer]
        Exporters[Export Modules]
        Holidays[Holiday Service]
        State[State Management]
    end
    
    subgraph "Data Layer"
        FileStore[(File Storage)]
        StateDB[(State Database)]
        Cache[(Redis Cache)]
        Logs[(Log Storage)]
    end
    
    subgraph "External Services"
        HRIS[HR Systems]
        Payroll[Payroll Systems]
        HolidayAPI[Government Holiday API]
        Notifications[Notification Services]
    end
    
    Web --> Gateway
    Mobile --> Gateway
    CLI --> FastAPI
    
    Gateway --> FastAPI
    Gateway --> Auth
    Gateway --> RateLimit
    
    FastAPI --> Analyzer
    FastAPI --> Background
    Background --> Scheduler
    
    Analyzer --> Exporters
    Analyzer --> Holidays
    Analyzer --> State
    
    FastAPI --> FileStore
    State --> StateDB
    FastAPI --> Cache
    FastAPI --> Logs
    
    Holidays --> HolidayAPI
    Background --> HRIS
    Background --> Payroll
    Background --> Notifications
```

### Technology Stack Matrix

| Layer | Technology | Purpose | Alternatives |
|-------|------------|---------|--------------|
| **Frontend** | Vanilla JS + i18next | Lightweight UI | React, Vue.js, Angular |
| **Web Server** | FastAPI + Uvicorn | REST API Server | Django REST, Flask, Express |
| **Authentication** | JWT + OAuth2/SAML | Security | Firebase Auth, Auth0, Keycloak |
| **API Gateway** | Kong, AWS ALB, Nginx | Traffic Management | Traefik, Istio, CloudFlare |
| **Containerization** | Docker + Docker Compose | Local Development | Kubernetes, Podman |
| **Orchestration** | Docker Swarm (simple) | Production Deploy | Kubernetes, ECS, GKE |
| **File Storage** | Local Filesystem | File Persistence | S3, Azure Blob, GCS |
| **State Store** | JSON Files | Simple State | PostgreSQL, MongoDB, Redis |
| **Caching** | In-Memory | Performance | Redis, Memcached, Hazelcast |
| **Monitoring** | Python Logging | Observability | Prometheus, ELK, DataDog |

## Deployment Architecture Patterns

### 1. Single-Tenant Development/Small Business

```yaml
# docker-compose-dev.yml
version: '3.8'
services:
  fhr:
    build: .
    ports:
      - "8000:8000"
    environment:
      - ENVIRONMENT=development
      - LOG_LEVEL=DEBUG
      - FHR_STATE_FILE=/app/data/attendance_state.json
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=3)"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

**Characteristics:**
- Single container deployment
- Local file storage
- Basic health checks
- Development/debugging friendly
- Cost-effective for small deployments

### 2. Multi-Tenant Enterprise with High Availability

```yaml
# docker-compose-enterprise.yml
version: '3.8'
services:
  # Load Balancer
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      - fhr-app-1
      - fhr-app-2

  # Application Instances
  fhr-app-1:
    build: .
    environment:
      - ENVIRONMENT=production
      - INSTANCE_ID=app-1
      - DATABASE_URL=postgresql://user:pass@postgres:5432/fhr
      - REDIS_URL=redis://redis:6379/0
      - S3_BUCKET=fhr-enterprise-storage
    volumes:
      - app1-data:/app/data
    depends_on:
      - postgres
      - redis
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=3)"]
      interval: 30s
      timeout: 10s
      retries: 3
      
  fhr-app-2:
    build: .
    environment:
      - ENVIRONMENT=production  
      - INSTANCE_ID=app-2
      - DATABASE_URL=postgresql://user:pass@postgres:5432/fhr
      - REDIS_URL=redis://redis:6379/0
      - S3_BUCKET=fhr-enterprise-storage
    volumes:
      - app2-data:/app/data
    depends_on:
      - postgres
      - redis

  # Database
  postgres:
    image: postgres:15-alpine
    environment:
      - POSTGRES_DB=fhr
      - POSTGRES_USER=fhruser
      - POSTGRES_PASSWORD_FILE=/run/secrets/postgres_password
    volumes:
      - postgres-data:/var/lib/postgresql/data
      - ./init-db.sql:/docker-entrypoint-initdb.d/init.sql:ro
    secrets:
      - postgres_password

  # Cache
  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD}
    volumes:
      - redis-data:/data

  # Monitoring
  prometheus:
    image: prom/prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus-data:/prometheus

  grafana:
    image: grafana/grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD_FILE=/run/secrets/grafana_password
    volumes:
      - grafana-data:/var/lib/grafana
      - ./grafana-dashboards:/etc/grafana/provisioning/dashboards:ro
    secrets:
      - grafana_password

volumes:
  app1-data:
  app2-data:
  postgres-data:
  redis-data:
  prometheus-data:
  grafana-data:

secrets:
  postgres_password:
    external: true
  grafana_password:
    external: true
```

### 3. Kubernetes Deployment Pattern

```yaml
# k8s-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: fhr-app
  namespace: fhr-system
  labels:
    app: fhr
    version: v2.0.0
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
      maxSurge: 1
  selector:
    matchLabels:
      app: fhr
  template:
    metadata:
      labels:
        app: fhr
        version: v2.0.0
    spec:
      containers:
      - name: fhr
        image: fhr:v2.0.0
        ports:
        - containerPort: 8000
          name: http
        env:
        - name: ENVIRONMENT
          value: "production"
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: fhr-secrets
              key: database-url
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: fhr-secrets
              key: redis-url
        - name: S3_BUCKET
          valueFrom:
            configMapKeyRef:
              name: fhr-config
              key: s3-bucket
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /api/health
            port: http
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /api/health
            port: http
          initialDelaySeconds: 5
          periodSeconds: 5
        volumeMounts:
        - name: fhr-data
          mountPath: /app/data
        - name: fhr-logs
          mountPath: /app/logs
      volumes:
      - name: fhr-data
        persistentVolumeClaim:
          claimName: fhr-data-pvc
      - name: fhr-logs
        emptyDir: {}
      
---
apiVersion: v1
kind: Service
metadata:
  name: fhr-service
  namespace: fhr-system
spec:
  selector:
    app: fhr
  ports:
  - protocol: TCP
    port: 80
    targetPort: http
  type: ClusterIP

---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: fhr-ingress
  namespace: fhr-system
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/rate-limit: "100"
    nginx.ingress.kubernetes.io/rate-limit-window: "1m"
spec:
  tls:
  - hosts:
    - fhr.company.com
    secretName: fhr-tls
  rules:
  - host: fhr.company.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: fhr-service
            port:
              number: 80
```

## Service Configuration Management

### 1. Environment-Based Configuration

```python
# lib/config.py (Enhanced)
import os
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

class Environment(Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"

@dataclass
class DatabaseConfig:
    url: str
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30
    
@dataclass
class RedisConfig:
    url: str
    max_connections: int = 10
    socket_timeout: int = 30
    
@dataclass
class S3Config:
    bucket: str
    region: str = "us-west-2"
    access_key_id: Optional[str] = None
    secret_access_key: Optional[str] = None
    endpoint_url: Optional[str] = None  # For MinIO/localstack
    
@dataclass
class SecurityConfig:
    jwt_secret: str
    jwt_expire_minutes: int = 60
    api_key_header: str = "X-API-Key"
    tenant_header: str = "X-Tenant-ID"
    cors_origins: list = field(default_factory=list)
    
@dataclass
class MonitoringConfig:
    prometheus_port: int = 9090
    log_level: str = "INFO"
    sentry_dsn: Optional[str] = None
    
@dataclass
class ServiceConfig:
    environment: Environment
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1
    
    # Storage
    database: Optional[DatabaseConfig] = None
    redis: Optional[RedisConfig] = None
    s3: Optional[S3Config] = None
    
    # Security
    security: SecurityConfig = field(default_factory=lambda: SecurityConfig(jwt_secret="dev-secret"))
    
    # Monitoring
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    
    # Business Logic
    state_file: str = "attendance_state.json"
    upload_max_size: int = 50 * 1024 * 1024  # 50MB
    analysis_timeout: int = 300  # 5 minutes
    
    @classmethod
    def from_env(cls) -> 'ServiceConfig':
        """Load configuration from environment variables."""
        env_name = os.getenv("ENVIRONMENT", "development")
        environment = Environment(env_name)
        
        config = cls(
            environment=environment,
            debug=os.getenv("DEBUG", "false").lower() == "true",
            host=os.getenv("HOST", "0.0.0.0"),
            port=int(os.getenv("PORT", "8000")),
            workers=int(os.getenv("WORKERS", "1")),
            state_file=os.getenv("FHR_STATE_FILE", "attendance_state.json"),
            upload_max_size=int(os.getenv("UPLOAD_MAX_SIZE", str(50 * 1024 * 1024))),
        )
        
        # Database configuration
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            config.database = DatabaseConfig(
                url=database_url,
                pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
                max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20"))
            )
        
        # Redis configuration
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            config.redis = RedisConfig(
                url=redis_url,
                max_connections=int(os.getenv("REDIS_MAX_CONNECTIONS", "10"))
            )
        
        # S3 configuration
        s3_bucket = os.getenv("S3_BUCKET")
        if s3_bucket:
            config.s3 = S3Config(
                bucket=s3_bucket,
                region=os.getenv("S3_REGION", "us-west-2"),
                access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                endpoint_url=os.getenv("S3_ENDPOINT_URL")
            )
        
        # Security configuration
        config.security = SecurityConfig(
            jwt_secret=os.getenv("JWT_SECRET", "dev-secret-change-in-production"),
            jwt_expire_minutes=int(os.getenv("JWT_EXPIRE_MINUTES", "60")),
            cors_origins=os.getenv("CORS_ORIGINS", "").split(",") if os.getenv("CORS_ORIGINS") else ["*"]
        )
        
        # Monitoring configuration
        config.monitoring = MonitoringConfig(
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            sentry_dsn=os.getenv("SENTRY_DSN")
        )
        
        return config
    
    def validate(self) -> list[str]:
        """Validate configuration and return list of errors."""
        errors = []
        
        if self.environment == Environment.PRODUCTION:
            if self.security.jwt_secret == "dev-secret":
                errors.append("JWT secret must be changed in production")
            if self.debug:
                errors.append("Debug mode should be disabled in production")
            if "*" in self.security.cors_origins:
                errors.append("CORS origins should be restricted in production")
        
        if self.upload_max_size > 100 * 1024 * 1024:  # 100MB
            errors.append("Upload max size should not exceed 100MB")
            
        return errors
```

### 2. Service Discovery and Load Balancing

```python
# lib/service_discovery.py
import asyncio
import aiohttp
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass
class ServiceInstance:
    host: str
    port: int
    health_check_url: str
    last_health_check: Optional[datetime] = None
    healthy: bool = True
    metadata: Dict[str, str] = None
    
class ServiceRegistry:
    """Simple service registry for multi-instance deployments."""
    
    def __init__(self):
        self.instances: Dict[str, List[ServiceInstance]] = {}
        self.health_check_interval = 30  # seconds
        
    def register_instance(self, service_name: str, instance: ServiceInstance):
        """Register a service instance."""
        if service_name not in self.instances:
            self.instances[service_name] = []
        self.instances[service_name].append(instance)
        
    def get_healthy_instances(self, service_name: str) -> List[ServiceInstance]:
        """Get all healthy instances of a service."""
        if service_name not in self.instances:
            return []
        return [inst for inst in self.instances[service_name] if inst.healthy]
        
    async def health_check_loop(self):
        """Continuously monitor instance health."""
        while True:
            await self.check_all_instances()
            await asyncio.sleep(self.health_check_interval)
            
    async def check_all_instances(self):
        """Check health of all registered instances."""
        tasks = []
        for service_name, instances in self.instances.items():
            for instance in instances:
                tasks.append(self._check_instance_health(instance))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _check_instance_health(self, instance: ServiceInstance):
        """Check health of a single instance."""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(instance.health_check_url) as response:
                    instance.healthy = response.status == 200
                    instance.last_health_check = datetime.utcnow()
        except Exception:
            instance.healthy = False
            instance.last_health_check = datetime.utcnow()

class LoadBalancer:
    """Simple load balancer for distributing requests."""
    
    def __init__(self, service_registry: ServiceRegistry):
        self.registry = service_registry
        self.round_robin_counters: Dict[str, int] = {}
        
    def get_instance(self, service_name: str, strategy: str = "round_robin") -> Optional[ServiceInstance]:
        """Get an instance using the specified load balancing strategy."""
        healthy_instances = self.registry.get_healthy_instances(service_name)
        
        if not healthy_instances:
            return None
            
        if strategy == "round_robin":
            return self._round_robin_select(service_name, healthy_instances)
        elif strategy == "random":
            import random
            return random.choice(healthy_instances)
        elif strategy == "least_connections":
            # Would need to track active connections per instance
            return self._least_connections_select(healthy_instances)
        else:
            return healthy_instances[0]  # First available
            
    def _round_robin_select(self, service_name: str, instances: List[ServiceInstance]) -> ServiceInstance:
        """Select instance using round-robin strategy."""
        if service_name not in self.round_robin_counters:
            self.round_robin_counters[service_name] = 0
            
        counter = self.round_robin_counters[service_name]
        instance = instances[counter % len(instances)]
        self.round_robin_counters[service_name] = counter + 1
        
        return instance
    
    def _least_connections_select(self, instances: List[ServiceInstance]) -> ServiceInstance:
        """Select instance with least active connections (simplified)."""
        # In a real implementation, you'd track active connections
        # For now, just return the first instance
        return instances[0]
```

## Service Metrics and Monitoring

### 1. Application Metrics

```python
# lib/metrics.py
import time
import psutil
from typing import Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict, deque

class MetricsCollector:
    """Collect application metrics for monitoring and alerting."""
    
    def __init__(self):
        self.request_counts = defaultdict(int)
        self.response_times = defaultdict(deque)
        self.error_counts = defaultdict(int)
        self.active_analyses = 0
        self.total_analyses = 0
        self.start_time = datetime.utcnow()
        
    def record_request(self, endpoint: str, method: str, status_code: int, response_time: float):
        """Record request metrics."""
        key = f"{method}:{endpoint}"
        self.request_counts[key] += 1
        
        # Keep last 1000 response times for percentile calculations
        response_times = self.response_times[key]
        response_times.append(response_time)
        if len(response_times) > 1000:
            response_times.popleft()
            
        if status_code >= 400:
            self.error_counts[key] += 1
    
    def start_analysis(self):
        """Record start of analysis."""
        self.active_analyses += 1
        self.total_analyses += 1
        
    def complete_analysis(self):
        """Record completion of analysis."""
        self.active_analyses = max(0, self.active_analyses - 1)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics snapshot."""
        uptime = datetime.utcnow() - self.start_time
        
        # Calculate response time percentiles
        percentiles = {}
        for endpoint, times in self.response_times.items():
            if times:
                sorted_times = sorted(times)
                percentiles[f"{endpoint}_p50"] = self._percentile(sorted_times, 50)
                percentiles[f"{endpoint}_p95"] = self._percentile(sorted_times, 95)
                percentiles[f"{endpoint}_p99"] = self._percentile(sorted_times, 99)
        
        # System metrics
        process = psutil.Process()
        memory_info = process.memory_info()
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "uptime_seconds": uptime.total_seconds(),
            
            # Application metrics
            "active_analyses": self.active_analyses,
            "total_analyses": self.total_analyses,
            "request_counts": dict(self.request_counts),
            "error_counts": dict(self.error_counts),
            "response_time_percentiles": percentiles,
            
            # System metrics
            "memory_usage_mb": memory_info.rss / 1024 / 1024,
            "memory_usage_percent": process.memory_percent(),
            "cpu_usage_percent": process.cpu_percent(),
            "open_files": len(process.open_files()),
            "num_threads": process.num_threads(),
            
            # System-wide metrics
            "system_cpu_percent": psutil.cpu_percent(),
            "system_memory_percent": psutil.virtual_memory().percent,
            "disk_usage_percent": psutil.disk_usage('/').percent,
        }
    
    def _percentile(self, sorted_data: list, percentile: int) -> float:
        """Calculate percentile from sorted data."""
        if not sorted_data:
            return 0.0
        index = (len(sorted_data) - 1) * percentile / 100.0
        lower = int(index)
        upper = min(lower + 1, len(sorted_data) - 1)
        weight = index - lower
        return sorted_data[lower] * (1 - weight) + sorted_data[upper] * weight

# Middleware for automatic metrics collection
from fastapi import Request, Response
import time

async def metrics_middleware(request: Request, call_next):
    """FastAPI middleware to automatically collect request metrics."""
    start_time = time.time()
    
    response = await call_next(request)
    
    response_time = time.time() - start_time
    
    # Get metrics collector from app state
    metrics_collector = request.app.state.metrics_collector
    
    metrics_collector.record_request(
        endpoint=request.url.path,
        method=request.method,
        status_code=response.status_code,
        response_time=response_time
    )
    
    return response
```

### 2. Health Check Implementation

```python
# Enhanced health check endpoint
from fastapi import HTTPException
from typing import Dict, Any

async def detailed_health_check() -> Dict[str, Any]:
    """
    Comprehensive health check including dependencies.
    
    Returns detailed status information for monitoring systems.
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "2.0.0",
        "environment": config.environment.value,
        "uptime_seconds": (datetime.utcnow() - app.state.start_time).total_seconds(),
        "checks": {}
    }
    
    overall_healthy = True
    
    # Check database connection
    try:
        if config.database:
            # Test database query
            await test_database_connection()
            health_status["checks"]["database"] = {"status": "healthy", "response_time_ms": 10}
        else:
            health_status["checks"]["database"] = {"status": "not_configured"}
    except Exception as e:
        health_status["checks"]["database"] = {"status": "unhealthy", "error": str(e)}
        overall_healthy = False
    
    # Check Redis connection
    try:
        if config.redis:
            await test_redis_connection()
            health_status["checks"]["redis"] = {"status": "healthy", "response_time_ms": 5}
        else:
            health_status["checks"]["redis"] = {"status": "not_configured"}
    except Exception as e:
        health_status["checks"]["redis"] = {"status": "unhealthy", "error": str(e)}
        overall_healthy = False
    
    # Check file storage
    try:
        await test_file_storage()
        health_status["checks"]["file_storage"] = {"status": "healthy"}
    except Exception as e:
        health_status["checks"]["file_storage"] = {"status": "unhealthy", "error": str(e)}
        overall_healthy = False
    
    # Check holiday API
    try:
        await test_holiday_api()
        health_status["checks"]["holiday_api"] = {"status": "healthy"}
    except Exception as e:
        health_status["checks"]["holiday_api"] = {"status": "degraded", "error": str(e)}
        # Holiday API failure doesn't make the service unhealthy (has fallback)
    
    # Check system resources
    try:
        memory_percent = psutil.virtual_memory().percent
        disk_percent = psutil.disk_usage('/').percent
        
        resource_status = "healthy"
        if memory_percent > 90 or disk_percent > 90:
            resource_status = "warning"
            overall_healthy = False
        if memory_percent > 95 or disk_percent > 95:
            resource_status = "critical"
            overall_healthy = False
        
        health_status["checks"]["system_resources"] = {
            "status": resource_status,
            "memory_percent": memory_percent,
            "disk_percent": disk_percent
        }
    except Exception as e:
        health_status["checks"]["system_resources"] = {"status": "unknown", "error": str(e)}
    
    # Get application metrics
    metrics_collector = app.state.metrics_collector
    app_metrics = metrics_collector.get_metrics()
    health_status["metrics"] = {
        "active_analyses": app_metrics["active_analyses"],
        "total_analyses": app_metrics["total_analyses"],
        "memory_usage_mb": app_metrics["memory_usage_mb"],
        "cpu_usage_percent": app_metrics["cpu_usage_percent"]
    }
    
    if not overall_healthy:
        health_status["status"] = "unhealthy"
    
    return health_status

# Add health check endpoints
@app.get("/api/health")
async def health():
    """Simple health check for load balancers."""
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

@app.get("/api/health/detailed")
async def health_detailed():
    """Detailed health check for monitoring systems."""
    return await detailed_health_check()

@app.get("/api/metrics")
async def metrics():
    """Prometheus-compatible metrics endpoint."""
    metrics_collector = app.state.metrics_collector
    metrics_data = metrics_collector.get_metrics()
    
    # Convert to Prometheus format
    prometheus_metrics = []
    prometheus_metrics.append(f"fhr_active_analyses {metrics_data['active_analyses']}")
    prometheus_metrics.append(f"fhr_total_analyses {metrics_data['total_analyses']}")
    prometheus_metrics.append(f"fhr_memory_usage_mb {metrics_data['memory_usage_mb']}")
    prometheus_metrics.append(f"fhr_cpu_usage_percent {metrics_data['cpu_usage_percent']}")
    
    return Response("\n".join(prometheus_metrics), media_type="text/plain")
```

## Scalability Patterns

### 1. Horizontal Scaling Strategy

```yaml
# Auto-scaling configuration for Kubernetes
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: fhr-hpa
  namespace: fhr-system
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: fhr-app
  minReplicas: 2
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Percent
        value: 10
        periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
      - type: Percent
        value: 50
        periodSeconds: 15
      - type: Pods
        value: 2
        periodSeconds: 60
      selectPolicy: Max
```

### 2. Background Job Processing

```python
# lib/background_jobs.py
import asyncio
from typing import Dict, Any, Callable
from datetime import datetime
from enum import Enum
from dataclasses import dataclass

class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class BackgroundJob:
    job_id: str
    job_type: str
    status: JobStatus
    created_at: datetime
    started_at: datetime = None
    completed_at: datetime = None
    progress: float = 0.0
    result: Any = None
    error: str = None
    metadata: Dict[str, Any] = None

class BackgroundJobManager:
    """Manage long-running background jobs (analysis, export, cleanup)."""
    
    def __init__(self, max_concurrent_jobs: int = 5):
        self.jobs: Dict[str, BackgroundJob] = {}
        self.job_handlers: Dict[str, Callable] = {}
        self.max_concurrent_jobs = max_concurrent_jobs
        self.running_jobs = 0
        self.job_queue = asyncio.Queue()
        
    def register_handler(self, job_type: str, handler: Callable):
        """Register a handler for a job type."""
        self.job_handlers[job_type] = handler
        
    async def submit_job(self, job_type: str, job_data: Dict[str, Any]) -> str:
        """Submit a job for background processing."""
        job_id = f"{job_type}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{id(job_data)}"
        
        job = BackgroundJob(
            job_id=job_id,
            job_type=job_type,
            status=JobStatus.PENDING,
            created_at=datetime.utcnow(),
            metadata=job_data
        )
        
        self.jobs[job_id] = job
        await self.job_queue.put(job_id)
        
        return job_id
    
    async def get_job_status(self, job_id: str) -> BackgroundJob:
        """Get the status of a job."""
        return self.jobs.get(job_id)
    
    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending or running job."""
        job = self.jobs.get(job_id)
        if job and job.status in [JobStatus.PENDING, JobStatus.RUNNING]:
            job.status = JobStatus.CANCELLED
            return True
        return False
    
    async def start_job_processor(self):
        """Start the background job processor."""
        while True:
            try:
                if self.running_jobs < self.max_concurrent_jobs:
                    # Get next job from queue
                    job_id = await self.job_queue.get()
                    job = self.jobs.get(job_id)
                    
                    if job and job.status == JobStatus.PENDING:
                        # Start job processing
                        asyncio.create_task(self._process_job(job))
                        
            except Exception as e:
                print(f"Error in job processor: {e}")
                await asyncio.sleep(1)
    
    async def _process_job(self, job: BackgroundJob):
        """Process a single job."""
        try:
            self.running_jobs += 1
            job.status = JobStatus.RUNNING
            job.started_at = datetime.utcnow()
            
            # Get handler for job type
            handler = self.job_handlers.get(job.job_type)
            if not handler:
                raise ValueError(f"No handler registered for job type: {job.job_type}")
            
            # Execute job with progress callback
            def progress_callback(progress: float):
                job.progress = min(100.0, max(0.0, progress))
            
            result = await handler(job.metadata, progress_callback)
            
            job.status = JobStatus.COMPLETED
            job.result = result
            job.progress = 100.0
            job.completed_at = datetime.utcnow()
            
        except Exception as e:
            job.status = JobStatus.FAILED
            job.error = str(e)
            job.completed_at = datetime.utcnow()
            
        finally:
            self.running_jobs -= 1
    
    def cleanup_old_jobs(self, max_age_hours: int = 24):
        """Clean up old completed/failed jobs."""
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        
        jobs_to_remove = []
        for job_id, job in self.jobs.items():
            if (job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED] and 
                job.completed_at and job.completed_at < cutoff):
                jobs_to_remove.append(job_id)
        
        for job_id in jobs_to_remove:
            del self.jobs[job_id]

# Job handlers
async def analyze_file_job(job_data: Dict[str, Any], progress_callback: Callable[[float], None]) -> Dict[str, Any]:
    """Background job handler for file analysis."""
    file_path = job_data["file_path"]
    mode = job_data.get("mode", "incremental")
    output_format = job_data.get("output_format", "excel")
    
    progress_callback(10.0)  # Starting analysis
    
    # Create analyzer
    analyzer = AttendanceAnalyzer()
    analyzer.parse_attendance_file(file_path, incremental=(mode == "incremental"))
    progress_callback(30.0)  # Parsed file
    
    analyzer.group_records_by_day()
    progress_callback(50.0)  # Grouped records
    
    analyzer.analyze_attendance()
    progress_callback(80.0)  # Completed analysis
    
    # Generate output file
    output_path = file_path.replace(".txt", f"_analysis.{output_format}")
    analyzer.export_report(output_path, output_format)
    progress_callback(100.0)  # Export completed
    
    return {
        "output_path": output_path,
        "total_issues": len(analyzer.issues),
        "analysis_mode": mode,
        "output_format": output_format
    }
```

This service architecture documentation provides comprehensive patterns for deploying, scaling, and operating the FHR system in enterprise environments with proper monitoring, health checking, and background job processing capabilities.