# API Documentation Architecture

## Overview

The FHR system provides a comprehensive FastAPI-based web service with auto-generated OpenAPI documentation. This document outlines the documentation architecture for enterprise API management.

## OpenAPI Integration Strategy

### Current Implementation
- **Auto-generated docs**: Available at `/docs` (Swagger UI) and `/openapi.json`
- **Pydantic Models**: Strong typing with `IssueDTO`, `StatusDTO`, `AnalyzeResponse`
- **Form-based uploads**: Multipart/form-data for file uploads with metadata

### Enterprise Enhancement Recommendations

#### 1. API Versioning Documentation
```python
# Recommended API versioning strategy
app = FastAPI(
    title="FHR Enterprise Attendance API",
    version="v2.0.0",
    description="Enterprise attendance analysis with multi-tenant support",
    openapi_url="/api/v2/openapi.json",
    docs_url="/api/v2/docs",
    redoc_url="/api/v2/redoc"
)

# Version-specific routers
from fastapi import APIRouter
v1_router = APIRouter(prefix="/api/v1", tags=["v1-legacy"])
v2_router = APIRouter(prefix="/api/v2", tags=["v2-current"])
```

#### 2. Enhanced Response Models
```python
class EnterpriseAnalyzeResponse(BaseModel):
    # Current fields...
    analysis_id: str
    user: Optional[str] = None
    
    # Enterprise additions
    tenant_id: str
    compliance_metadata: ComplianceMetadata
    audit_trail: List[AuditEvent]
    integration_webhooks: List[WebhookEvent]
    performance_metrics: PerformanceMetrics
    security_context: SecurityContext
    
    class Config:
        schema_extra = {
            "example": {
                "analysis_id": "20250914T143000_a1b2c3d4",
                "tenant_id": "company-abc-123",
                "user": "員工姓名",
                "compliance_metadata": {
                    "retention_policy": "7_years",
                    "data_classification": "PII_SENSITIVE",
                    "regulatory_requirements": ["GDPR", "Taiwan_Labor_Standards"]
                }
            }
        }
```

#### 3. Authentication & Authorization Documentation
```yaml
# OpenAPI security scheme
components:
  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-API-Key
    TenantAuth:
      type: apiKey
      in: header
      name: X-Tenant-ID

security:
  - BearerAuth: []
  - ApiKeyAuth: []
  - TenantAuth: []
```

## API Documentation Standards

### 1. Endpoint Documentation Template
```python
@app.post(
    "/api/v2/analyze",
    response_model=EnterpriseAnalyzeResponse,
    responses={
        200: {"description": "Analysis completed successfully"},
        400: {"description": "Invalid input parameters", "model": ErrorResponse},
        401: {"description": "Authentication failed", "model": AuthErrorResponse},
        403: {"description": "Insufficient permissions", "model": PermissionErrorResponse},
        413: {"description": "File too large", "model": FileSizeErrorResponse},
        422: {"description": "Validation error", "model": ValidationErrorResponse},
        429: {"description": "Rate limit exceeded", "model": RateLimitErrorResponse},
        500: {"description": "Internal server error", "model": ServerErrorResponse}
    },
    tags=["analysis"],
    summary="Analyze attendance data with enterprise features",
    description="""
    Analyzes uploaded attendance data with enterprise-grade features including:
    
    - Multi-tenant isolation
    - Audit logging
    - Compliance metadata
    - Integration webhooks
    - Performance monitoring
    
    **File Requirements:**
    - Format: Tab-separated text (.txt)
    - Size limit: 50MB per tenant tier
    - Naming convention: YYYYMM[-YYYYMM]-UserName-出勤資料.txt
    
    **Rate Limits:**
    - Standard tier: 10 requests/minute
    - Premium tier: 100 requests/minute
    - Enterprise tier: Unlimited
    
    **Data Retention:**
    - Upload files: Deleted after 30 days
    - Analysis results: Retained per tenant policy
    - Audit logs: 7 years minimum
    """,
    operation_id="analyze_attendance_enterprise",
    deprecated=False
)
```

### 2. Error Response Standardization
```python
class BaseErrorResponse(BaseModel):
    error_code: str
    message: str
    details: Optional[dict] = None
    timestamp: datetime
    trace_id: str
    tenant_id: Optional[str] = None

class ValidationErrorResponse(BaseErrorResponse):
    validation_errors: List[ValidationError]
    
class RateLimitErrorResponse(BaseErrorResponse):
    retry_after: int  # seconds
    current_limit: int
    reset_time: datetime
```

## Integration Documentation Patterns

### 1. Webhook Documentation
```python
class WebhookPayload(BaseModel):
    event_type: Literal["analysis.completed", "analysis.failed", "compliance.alert"]
    tenant_id: str
    analysis_id: str
    timestamp: datetime
    data: dict
    signature: str  # HMAC signature for verification

# Document webhook endpoints that clients should implement
webhook_docs = """
**Webhook Endpoints (Client Implementation Required)**

POST /webhooks/fhr/analysis-completed
- Receives analysis completion notifications
- Payload: WebhookPayload with event_type="analysis.completed"

POST /webhooks/fhr/compliance-alert
- Receives compliance violation alerts
- Payload: WebhookPayload with event_type="compliance.alert"
"""
```

### 2. SDK Code Examples
```python
# Include SDK examples in API docs
sdk_examples = {
    "python": """
import requests
from typing import Optional

class FHRClient:
    def __init__(self, api_key: str, tenant_id: str, base_url: str = "https://api.fhr.company.com"):
        self.api_key = api_key
        self.tenant_id = tenant_id
        self.base_url = base_url
    
    def analyze_file(self, file_path: str, mode: str = "incremental", 
                    output: str = "excel") -> dict:
        headers = {
            "X-API-Key": self.api_key,
            "X-Tenant-ID": self.tenant_id
        }
        
        with open(file_path, 'rb') as f:
            files = {"file": f}
            data = {"mode": mode, "output": output}
            
            response = requests.post(
                f"{self.base_url}/api/v2/analyze",
                headers=headers,
                files=files,
                data=data
            )
            response.raise_for_status()
            return response.json()
""",
    "javascript": """
class FHRClient {
    constructor(apiKey, tenantId, baseUrl = 'https://api.fhr.company.com') {
        this.apiKey = apiKey;
        this.tenantId = tenantId;
        this.baseUrl = baseUrl;
    }
    
    async analyzeFile(file, mode = 'incremental', output = 'excel') {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('mode', mode);
        formData.append('output', output);
        
        const response = await fetch(`${this.baseUrl}/api/v2/analyze`, {
            method: 'POST',
            headers: {
                'X-API-Key': this.apiKey,
                'X-Tenant-ID': this.tenantId
            },
            body: formData
        });
        
        if (!response.ok) {
            throw new Error(`API request failed: ${response.statusText}`);
        }
        
        return await response.json();
    }
}
"""
}
```

## Performance Documentation

### 1. SLA Documentation
```markdown
## Service Level Agreements

### Response Times
- File upload (< 10MB): < 2 seconds
- Analysis processing: < 30 seconds per 1000 records
- Report generation: < 10 seconds
- Download initiation: < 1 second

### Availability
- Production: 99.9% uptime (excluding planned maintenance)
- Staging: 99.5% uptime
- Development: Best effort

### Throughput
- Concurrent analyses per tenant: 5 (Standard), 20 (Premium), Unlimited (Enterprise)
- Maximum file size: 10MB (Standard), 50MB (Premium), 100MB (Enterprise)
- API rate limits: See endpoint documentation
```

### 2. Monitoring Endpoints
```python
@app.get("/api/v2/metrics", tags=["monitoring"])
def get_metrics():
    """
    Returns system metrics for monitoring and alerting.
    
    Requires monitoring role or system API key.
    """
    return {
        "active_analyses": get_active_analysis_count(),
        "queue_depth": get_queue_depth(),
        "average_processing_time": get_average_processing_time(),
        "error_rate_1h": get_error_rate(hours=1),
        "memory_usage": get_memory_usage(),
        "disk_usage": get_disk_usage(),
        "database_connections": get_db_connection_count()
    }

@app.get("/api/v2/health/detailed", tags=["monitoring"])
def detailed_health_check():
    """
    Comprehensive health check including dependencies.
    """
    return {
        "status": "healthy",
        "version": "2.0.0",
        "environment": "production",
        "dependencies": {
            "database": check_database_connection(),
            "redis_cache": check_redis_connection(),
            "file_storage": check_file_storage(),
            "holiday_api": check_holiday_api(),
            "webhook_endpoints": check_webhook_connectivity()
        },
        "timestamp": datetime.utcnow().isoformat()
    }
```

## Documentation Automation

### 1. Automated API Docs Generation
```python
# Custom OpenAPI schema generator
from fastapi.openapi.utils import get_openapi

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
        
    openapi_schema = get_openapi(
        title="FHR Enterprise API",
        version="2.0.0",
        description="Enterprise attendance analysis system",
        routes=app.routes,
    )
    
    # Add enterprise-specific documentation
    openapi_schema["info"]["x-logo"] = {
        "url": "https://api.fhr.company.com/static/logo.png"
    }
    
    openapi_schema["info"]["contact"] = {
        "name": "FHR Support",
        "url": "https://support.fhr.company.com",
        "email": "api-support@company.com"
    }
    
    openapi_schema["info"]["license"] = {
        "name": "Enterprise License",
        "url": "https://company.com/licenses/fhr-enterprise"
    }
    
    # Add authentication flows
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT"
        }
    }
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi
```

### 2. Documentation Testing
```python
# Test that API documentation is complete and accurate
import pytest
from fastapi.testclient import TestClient

def test_openapi_schema_completeness():
    """Ensure all endpoints have proper documentation."""
    client = TestClient(app)
    response = client.get("/openapi.json")
    schema = response.json()
    
    # Verify all endpoints have descriptions
    for path, methods in schema["paths"].items():
        for method, details in methods.items():
            assert "summary" in details, f"{method.upper()} {path} missing summary"
            assert "description" in details, f"{method.upper()} {path} missing description"
            assert "responses" in details, f"{method.upper()} {path} missing responses"
            
            # Check for proper error response documentation
            if method in ["post", "put", "patch"]:
                assert "400" in details["responses"], f"{method.upper()} {path} missing 400 response"
                assert "422" in details["responses"], f"{method.upper()} {path} missing 422 response"

def test_example_requests_valid():
    """Ensure example requests in documentation are valid."""
    client = TestClient(app)
    
    # Test documented examples
    example_request = {
        "file": ("test.txt", "sample data", "text/plain"),
        "mode": "incremental",
        "output": "excel"
    }
    
    # This should match the documented example format
    response = client.post("/api/v2/analyze", files=example_request)
    assert response.status_code in [200, 400, 422]  # Should not be 500
```

## Enterprise API Gateway Integration

### 1. API Gateway Configuration Template
```yaml
# Kong/AWS API Gateway configuration template
apiVersion: configuration.konghq.com/v1
kind: KongPlugin
metadata:
  name: fhr-rate-limiting
config:
  minute: 100
  hour: 1000
  day: 10000
  policy: cluster
  header_name: X-Tenant-ID
  fault_tolerant: true
---
apiVersion: configuration.konghq.com/v1
kind: KongPlugin
metadata:
  name: fhr-authentication
config:
  key_names: ["X-API-Key"]
  hide_credentials: true
---
# API Gateway route configuration
apiVersion: configuration.konghq.com/v1
kind: KongIngress
metadata:
  name: fhr-api
spec:
  route:
    plugins:
    - fhr-rate-limiting
    - fhr-authentication
    - cors
    - request-transformer
    - response-transformer
    paths: ["/api/v2/*"]
    methods: ["GET", "POST", "PUT", "DELETE"]
    protocols: ["https"]
    strip_path: false
```

This comprehensive API documentation architecture provides enterprise-ready patterns for scaling the FHR system while maintaining clarity and developer experience.