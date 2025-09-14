# Documentation Automation Framework

## Overview

Documentation automation is critical for maintaining up-to-date, accurate, and comprehensive documentation in enterprise software systems. This framework outlines automated processes for generating, maintaining, and validating documentation across the FHR attendance analysis system.

## Documentation Automation Strategy

```mermaid
graph TB
    subgraph "Source Code Analysis"
        AST[Abstract Syntax Tree Analysis]
        Comments[Code Comment Extraction]
        Types[Type Annotation Analysis]
        Tests[Test Case Documentation]
    end
    
    subgraph "API Documentation"
        OpenAPI[OpenAPI Schema Generation]
        Examples[Request/Response Examples]
        SDKs[SDK Code Generation]
    end
    
    subgraph "Architecture Documentation"
        Diagrams[Mermaid Diagram Generation]
        Dependencies[Dependency Analysis]
        Flows[Data Flow Documentation]
    end
    
    subgraph "User Documentation"
        Tutorials[Interactive Tutorials]
        Examples[Usage Examples]
        FAQ[FAQ Generation from Issues]
    end
    
    subgraph "Output Formats"
        Website[Documentation Website]
        PDF[PDF Documents]
        Confluence[Confluence Pages]
        Wiki[Wiki Pages]
    end
    
    AST --> OpenAPI
    Comments --> API Documentation
    Types --> OpenAPI
    Tests --> Examples
    
    OpenAPI --> Website
    Diagrams --> Website
    Tutorials --> Website
    
    Website --> PDF
    Website --> Confluence
    Website --> Wiki
```

## 1. Automated Code Documentation

### Source Code Analysis Pipeline

```python
# tools/doc_automation/code_analyzer.py
import ast
import inspect
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from pathlib import Path
import re

@dataclass
class FunctionDoc:
    name: str
    module: str
    signature: str
    docstring: Optional[str]
    parameters: List[Dict[str, Any]]
    return_type: Optional[str]
    examples: List[str]
    raises: List[str]
    complexity: int  # Cyclomatic complexity

@dataclass
class ClassDoc:
    name: str
    module: str
    docstring: Optional[str]
    methods: List[FunctionDoc]
    attributes: List[Dict[str, Any]]
    inheritance: List[str]
    usage_examples: List[str]

@dataclass
class ModuleDoc:
    name: str
    path: str
    docstring: Optional[str]
    classes: List[ClassDoc]
    functions: List[FunctionDoc]
    imports: List[str]
    constants: List[Dict[str, Any]]

class CodeAnalyzer:
    """Automated code analysis for documentation generation."""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.modules: Dict[str, ModuleDoc] = {}
        
    def analyze_project(self) -> Dict[str, ModuleDoc]:
        """Analyze entire project and generate documentation structure."""
        python_files = list(self.project_root.rglob("*.py"))
        
        for file_path in python_files:
            if self._should_analyze_file(file_path):
                module_doc = self.analyze_module(file_path)
                self.modules[module_doc.name] = module_doc
        
        return self.modules
    
    def _should_analyze_file(self, file_path: Path) -> bool:
        """Determine if file should be analyzed."""
        exclude_patterns = [
            "test_*",
            "__pycache__",
            ".git",
            "build",
            "dist",
            "coverage_report"
        ]
        
        path_str = str(file_path)
        return not any(pattern in path_str for pattern in exclude_patterns)
    
    def analyze_module(self, file_path: Path) -> ModuleDoc:
        """Analyze a single Python module."""
        with open(file_path, 'r', encoding='utf-8') as f:
            source_code = f.read()
        
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            # Handle files with syntax errors gracefully
            return ModuleDoc(
                name=str(file_path.relative_to(self.project_root)),
                path=str(file_path),
                docstring="Error: Could not parse file",
                classes=[],
                functions=[],
                imports=[],
                constants=[]
            )
        
        module_name = str(file_path.relative_to(self.project_root)).replace("/", ".").replace(".py", "")
        
        # Extract module docstring
        module_docstring = ast.get_docstring(tree)
        
        # Extract imports
        imports = self._extract_imports(tree)
        
        # Extract constants
        constants = self._extract_constants(tree)
        
        # Extract classes and functions
        classes = []
        functions = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if self._is_top_level(tree, node):
                    class_doc = self._analyze_class(node, module_name, source_code)
                    classes.append(class_doc)
            elif isinstance(node, ast.FunctionDef):
                if self._is_top_level(tree, node) and not node.name.startswith('_'):
                    func_doc = self._analyze_function(node, module_name, source_code)
                    functions.append(func_doc)
        
        return ModuleDoc(
            name=module_name,
            path=str(file_path),
            docstring=module_docstring,
            classes=classes,
            functions=functions,
            imports=imports,
            constants=constants
        )
    
    def _analyze_class(self, node: ast.ClassDef, module_name: str, source_code: str) -> ClassDoc:
        """Analyze a class definition."""
        docstring = ast.get_docstring(node)
        
        # Extract methods
        methods = []
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and not item.name.startswith('_'):
                func_doc = self._analyze_function(item, f"{module_name}.{node.name}", source_code)
                methods.append(func_doc)
        
        # Extract attributes
        attributes = self._extract_class_attributes(node)
        
        # Extract inheritance
        inheritance = [self._get_base_name(base) for base in node.bases]
        
        return ClassDoc(
            name=node.name,
            module=module_name,
            docstring=docstring,
            methods=methods,
            attributes=attributes,
            inheritance=inheritance,
            usage_examples=self._extract_usage_examples(node, source_code)
        )
    
    def _analyze_function(self, node: ast.FunctionDef, module_name: str, source_code: str) -> FunctionDoc:
        """Analyze a function definition."""
        docstring = ast.get_docstring(node)
        
        # Extract signature
        signature = self._build_function_signature(node)
        
        # Extract parameters
        parameters = self._extract_parameters(node)
        
        # Extract return type
        return_type = self._extract_return_type(node)
        
        # Extract examples from docstring
        examples = self._extract_examples_from_docstring(docstring) if docstring else []
        
        # Extract raises information
        raises = self._extract_raises_from_docstring(docstring) if docstring else []
        
        # Calculate cyclomatic complexity
        complexity = self._calculate_complexity(node)
        
        return FunctionDoc(
            name=node.name,
            module=module_name,
            signature=signature,
            docstring=docstring,
            parameters=parameters,
            return_type=return_type,
            examples=examples,
            raises=raises,
            complexity=complexity
        )
    
    def _build_function_signature(self, node: ast.FunctionDef) -> str:
        """Build function signature string."""
        args = []
        
        # Regular arguments
        for arg in node.args.args:
            arg_str = arg.arg
            if arg.annotation:
                arg_str += f": {ast.unparse(arg.annotation)}"
            args.append(arg_str)
        
        # Default arguments
        num_defaults = len(node.args.defaults)
        if num_defaults > 0:
            for i, default in enumerate(node.args.defaults):
                arg_index = len(args) - num_defaults + i
                args[arg_index] += f" = {ast.unparse(default)}"
        
        # Return type annotation
        return_annotation = ""
        if node.returns:
            return_annotation = f" -> {ast.unparse(node.returns)}"
        
        return f"{node.name}({', '.join(args)}){return_annotation}"
    
    def _calculate_complexity(self, node: ast.FunctionDef) -> int:
        """Calculate cyclomatic complexity of a function."""
        complexity = 1  # Base complexity
        
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                complexity += 1
            elif isinstance(child, ast.ExceptHandler):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
        
        return complexity
    
    def generate_markdown_docs(self) -> Dict[str, str]:
        """Generate Markdown documentation from analyzed code."""
        docs = {}
        
        for module_name, module_doc in self.modules.items():
            markdown = self._generate_module_markdown(module_doc)
            docs[f"{module_name}.md"] = markdown
        
        # Generate index
        docs["index.md"] = self._generate_index_markdown()
        
        return docs
    
    def _generate_module_markdown(self, module_doc: ModuleDoc) -> str:
        """Generate Markdown documentation for a module."""
        lines = [
            f"# {module_doc.name}",
            "",
            f"**Path:** `{module_doc.path}`",
            ""
        ]
        
        if module_doc.docstring:
            lines.extend([
                "## Description",
                "",
                module_doc.docstring,
                ""
            ])
        
        # Imports
        if module_doc.imports:
            lines.extend([
                "## Dependencies",
                "",
                "```python"
            ])
            lines.extend(module_doc.imports)
            lines.extend(["```", ""])
        
        # Constants
        if module_doc.constants:
            lines.extend([
                "## Constants",
                ""
            ])
            for constant in module_doc.constants:
                lines.append(f"- **{constant['name']}**: `{constant['value']}` - {constant.get('description', '')}")
            lines.append("")
        
        # Classes
        for class_doc in module_doc.classes:
            lines.extend(self._generate_class_markdown(class_doc))
        
        # Functions
        for func_doc in module_doc.functions:
            lines.extend(self._generate_function_markdown(func_doc))
        
        return "\n".join(lines)
    
    def _generate_class_markdown(self, class_doc: ClassDoc) -> List[str]:
        """Generate Markdown documentation for a class."""
        lines = [
            f"## class {class_doc.name}",
            ""
        ]
        
        if class_doc.inheritance:
            inheritance_str = ", ".join(class_doc.inheritance)
            lines.extend([
                f"**Inherits from:** {inheritance_str}",
                ""
            ])
        
        if class_doc.docstring:
            lines.extend([
                class_doc.docstring,
                ""
            ])
        
        # Attributes
        if class_doc.attributes:
            lines.extend([
                "### Attributes",
                ""
            ])
            for attr in class_doc.attributes:
                lines.append(f"- **{attr['name']}** ({attr.get('type', 'Any')}): {attr.get('description', '')}")
            lines.append("")
        
        # Methods
        for method in class_doc.methods:
            method_lines = self._generate_function_markdown(method, is_method=True)
            lines.extend(method_lines)
        
        return lines
    
    def _generate_function_markdown(self, func_doc: FunctionDoc, is_method: bool = False) -> List[str]:
        """Generate Markdown documentation for a function or method."""
        prefix = "###" if is_method else "##"
        lines = [
            f"{prefix} {func_doc.name}",
            "",
            f"```python",
            func_doc.signature,
            "```",
            ""
        ]
        
        if func_doc.docstring:
            lines.extend([
                func_doc.docstring,
                ""
            ])
        
        # Parameters
        if func_doc.parameters:
            lines.extend([
                "**Parameters:**",
                ""
            ])
            for param in func_doc.parameters:
                param_desc = f"- **{param['name']}** ({param.get('type', 'Any')})"
                if param.get('default'):
                    param_desc += f", default: `{param['default']}`"
                param_desc += f": {param.get('description', 'No description')}"
                lines.append(param_desc)
            lines.append("")
        
        # Return value
        if func_doc.return_type:
            lines.extend([
                "**Returns:**",
                "",
                f"- {func_doc.return_type}",
                ""
            ])
        
        # Raises
        if func_doc.raises:
            lines.extend([
                "**Raises:**",
                ""
            ])
            for raise_info in func_doc.raises:
                lines.append(f"- {raise_info}")
            lines.append("")
        
        # Examples
        if func_doc.examples:
            lines.extend([
                "**Examples:**",
                ""
            ])
            for example in func_doc.examples:
                lines.extend([
                    "```python",
                    example,
                    "```",
                    ""
                ])
        
        # Complexity warning
        if func_doc.complexity > 10:
            lines.extend([
                f"⚠️ **High Complexity**: This function has a cyclomatic complexity of {func_doc.complexity}. Consider refactoring.",
                ""
            ])
        
        return lines

# Helper functions for AST analysis
    def _extract_imports(self, tree: ast.AST) -> List[str]:
        """Extract import statements."""
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(f"import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                names = ", ".join([alias.name for alias in node.names])
                imports.append(f"from {module} import {names}")
        return imports
    
    def _extract_constants(self, tree: ast.AST) -> List[Dict[str, Any]]:
        """Extract module-level constants."""
        constants = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and self._is_top_level(tree, node):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.isupper():
                        constants.append({
                            "name": target.id,
                            "value": ast.unparse(node.value),
                            "type": type(ast.literal_eval(node.value)).__name__ if self._is_literal(node.value) else "Unknown"
                        })
        return constants
```

### 2. API Documentation Automation

```python
# tools/doc_automation/api_doc_generator.py
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
import json
from typing import Dict, Any, List
from pathlib import Path
import yaml

class APIDocumentationGenerator:
    """Generate comprehensive API documentation from FastAPI application."""
    
    def __init__(self, app: FastAPI):
        self.app = app
        self.openapi_schema = None
        
    def generate_openapi_schema(self) -> Dict[str, Any]:
        """Generate enhanced OpenAPI schema."""
        if self.openapi_schema:
            return self.openapi_schema
        
        self.openapi_schema = get_openapi(
            title="FHR Enterprise Attendance Analysis API",
            version="2.0.0",
            description=self._get_api_description(),
            routes=self.app.routes,
        )
        
        # Enhance schema with additional information
        self._enhance_openapi_schema()
        
        return self.openapi_schema
    
    def _get_api_description(self) -> str:
        """Get comprehensive API description."""
        return """
# FHR Enterprise Attendance Analysis API

A comprehensive attendance analysis system for enterprise environments with support for:

- **Multi-tenant Architecture**: Isolated data processing per organization
- **Incremental Analysis**: Process only new attendance data efficiently  
- **Multiple Export Formats**: CSV and Excel output with professional formatting
- **Taiwan Holiday Integration**: Automatic holiday detection with government API integration
- **Audit Logging**: Complete audit trail for compliance requirements
- **Enterprise Integration**: HRIS, payroll, and notification system integration

## Authentication

This API uses JWT Bearer token authentication. Include your token in the Authorization header:

```
Authorization: Bearer <your-jwt-token>
```

## Rate Limits

- Standard tier: 10 requests/minute
- Premium tier: 100 requests/minute  
- Enterprise tier: Unlimited

## Data Formats

### Input Files
- Format: Tab-separated text (.txt)
- Encoding: UTF-8
- Maximum size: 50MB (varies by tier)
- Naming convention: `YYYYMM[-YYYYMM]-UserName-出勤資料.txt`

### Response Formats
All endpoints return JSON responses with consistent error handling and status codes.
        """
    
    def _enhance_openapi_schema(self):
        """Enhance OpenAPI schema with additional documentation."""
        schema = self.openapi_schema
        
        # Add security schemes
        if "components" not in schema:
            schema["components"] = {}
        
        schema["components"]["securitySchemes"] = {
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "JWT token for API authentication"
            },
            "ApiKeyAuth": {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Key",
                "description": "API key for service-to-service authentication"
            }
        }
        
        # Add global security
        schema["security"] = [
            {"BearerAuth": []},
            {"ApiKeyAuth": []}
        ]
        
        # Enhance response schemas
        self._add_response_examples()
        
        # Add error response schemas
        self._add_error_schemas()
        
        # Add webhook documentation
        self._add_webhook_documentation()
    
    def _add_response_examples(self):
        """Add comprehensive response examples."""
        schema = self.openapi_schema
        
        # Add examples to analyze endpoint
        if "/api/analyze" in schema["paths"]:
            analyze_endpoint = schema["paths"]["/api/analyze"]["post"]
            
            # Success response example
            success_example = {
                "analysis_id": "20240315T143000_a1b2c3d4",
                "user": "張小明",
                "mode": "incremental",
                "requested_mode": "incremental",
                "requested_format": "excel",
                "actual_format": "excel",
                "source_filename": "202403-張小明-出勤資料.txt",
                "output_filename": "build/api-outputs/session123/analysis.xlsx",
                "download_url": "/api/download/session123/analysis.xlsx",
                "first_time_user": False,
                "reset_requested": False,
                "reset_applied": False,
                "issues_preview": [
                    {
                        "date": "2024/03/15",
                        "type": "LATE",
                        "duration_minutes": 45,
                        "description": "遲到45分鐘",
                        "time_range": "09:15-18:30",
                        "calculation": "09:15 > 08:30，遲到45分鐘",
                        "status": "[NEW] 本次新發現"
                    }
                ],
                "totals": {
                    "FORGET_PUNCH": 2,
                    "LATE": 3,
                    "OVERTIME": 5,
                    "WFH": 8,
                    "WEEKDAY_LEAVE": 1,
                    "TOTAL": 19
                }
            }
            
            analyze_endpoint["responses"]["200"]["content"]["application/json"]["example"] = success_example
    
    def _add_error_schemas(self):
        """Add standardized error response schemas."""
        schema = self.openapi_schema
        
        error_schemas = {
            "ErrorResponse": {
                "type": "object",
                "properties": {
                    "error_code": {"type": "string"},
                    "message": {"type": "string"},
                    "details": {"type": "object"},
                    "timestamp": {"type": "string", "format": "date-time"},
                    "trace_id": {"type": "string"}
                },
                "required": ["error_code", "message", "timestamp"]
            },
            "ValidationErrorResponse": {
                "type": "object", 
                "properties": {
                    "detail": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "loc": {"type": "array", "items": {"type": "string"}},
                                "msg": {"type": "string"},
                                "type": {"type": "string"}
                            }
                        }
                    }
                }
            }
        }
        
        if "components" not in schema:
            schema["components"] = {}
        if "schemas" not in schema["components"]:
            schema["components"]["schemas"] = {}
        
        schema["components"]["schemas"].update(error_schemas)
    
    def generate_postman_collection(self) -> Dict[str, Any]:
        """Generate Postman collection from OpenAPI schema."""
        openapi = self.generate_openapi_schema()
        
        collection = {
            "info": {
                "name": openapi["info"]["title"],
                "description": openapi["info"]["description"],
                "version": openapi["info"]["version"],
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
            },
            "auth": {
                "type": "bearer",
                "bearer": [{"key": "token", "value": "{{jwt_token}}", "type": "string"}]
            },
            "variable": [
                {"key": "base_url", "value": "{{base_url}}", "type": "string"},
                {"key": "jwt_token", "value": "", "type": "string"}
            ],
            "item": []
        }
        
        # Convert OpenAPI paths to Postman requests
        for path, methods in openapi["paths"].items():
            folder = {
                "name": path,
                "item": []
            }
            
            for method, details in methods.items():
                request = self._create_postman_request(method.upper(), path, details)
                folder["item"].append(request)
            
            collection["item"].append(folder)
        
        return collection
    
    def _create_postman_request(self, method: str, path: str, details: Dict[str, Any]) -> Dict[str, Any]:
        """Create a Postman request from OpenAPI operation."""
        request = {
            "name": details.get("summary", f"{method} {path}"),
            "request": {
                "method": method,
                "header": [
                    {
                        "key": "Content-Type",
                        "value": "application/json",
                        "type": "text"
                    }
                ],
                "url": {
                    "raw": "{{base_url}}" + path,
                    "host": ["{{base_url}}"],
                    "path": path.split("/")[1:]
                },
                "description": details.get("description", "")
            },
            "response": []
        }
        
        # Add request body for POST/PUT requests
        if method in ["POST", "PUT", "PATCH"]:
            if "requestBody" in details:
                content = details["requestBody"]["content"]
                if "multipart/form-data" in content:
                    request["request"]["body"] = {
                        "mode": "formdata",
                        "formdata": [
                            {
                                "key": "file",
                                "type": "file",
                                "src": []
                            },
                            {
                                "key": "mode", 
                                "value": "incremental",
                                "type": "text"
                            },
                            {
                                "key": "output",
                                "value": "excel", 
                                "type": "text"
                            }
                        ]
                    }
                elif "application/json" in content:
                    request["request"]["body"] = {
                        "mode": "raw",
                        "raw": json.dumps(content["application/json"].get("example", {}), indent=2)
                    }
        
        return request
    
    def generate_sdk_documentation(self, languages: List[str] = ["python", "javascript", "curl"]) -> Dict[str, str]:
        """Generate SDK documentation and code examples."""
        openapi = self.generate_openapi_schema()
        sdk_docs = {}
        
        for language in languages:
            if language == "python":
                sdk_docs["python"] = self._generate_python_sdk_docs(openapi)
            elif language == "javascript":
                sdk_docs["javascript"] = self._generate_javascript_sdk_docs(openapi)
            elif language == "curl":
                sdk_docs["curl"] = self._generate_curl_examples(openapi)
        
        return sdk_docs
    
    def _generate_python_sdk_docs(self, openapi: Dict[str, Any]) -> str:
        """Generate Python SDK documentation."""
        return """
# FHR Python SDK

## Installation

```bash
pip install fhr-client
```

## Quick Start

```python
from fhr_client import FHRClient

# Initialize client
client = FHRClient(
    api_key="your-api-key",
    base_url="https://api.fhr.company.com"
)

# Analyze attendance file
with open("202403-張小明-出勤資料.txt", "rb") as f:
    result = client.analyze_file(
        file=f,
        mode="incremental",
        output_format="excel"
    )

print(f"Analysis ID: {result['analysis_id']}")
print(f"Total Issues: {result['totals']['TOTAL']}")

# Download results
client.download_file(
    analysis_id=result['analysis_id'],
    filename=result['output_filename']
)
```

## Complete SDK Implementation

```python
import requests
from typing import Optional, BinaryIO, Dict, Any
from pathlib import Path

class FHRClient:
    def __init__(self, api_key: str, base_url: str = "https://api.fhr.company.com"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "X-API-Key": api_key,
            "User-Agent": "FHR-Python-SDK/1.0.0"
        })
    
    def analyze_file(
        self,
        file: BinaryIO,
        filename: Optional[str] = None,
        mode: str = "incremental",
        output_format: str = "excel",
        reset_state: bool = False
    ) -> Dict[str, Any]:
        \"\"\"
        Analyze attendance file.
        
        Args:
            file: File-like object containing attendance data
            filename: Name of the file (auto-detected if not provided)
            mode: Analysis mode ("incremental" or "full")
            output_format: Output format ("excel" or "csv")
            reset_state: Whether to reset user state before analysis
            
        Returns:
            Dictionary containing analysis results
            
        Raises:
            FHRAPIError: If API request fails
        \"\"\"
        files = {"file": (filename or "attendance.txt", file, "text/plain")}
        data = {
            "mode": mode,
            "output": output_format,
            "reset_state": str(reset_state).lower()
        }
        
        response = self.session.post(
            f"{self.base_url}/api/analyze",
            files=files,
            data=data
        )
        
        if response.status_code != 200:
            raise FHRAPIError(f"Analysis failed: {response.status_code} {response.text}")
        
        return response.json()
    
    def download_file(self, analysis_id: str, filename: str, output_path: Optional[Path] = None) -> Path:
        \"\"\"Download analysis results.\"\"\"
        response = self.session.get(
            f"{self.base_url}/api/download/{analysis_id}/{filename}"
        )
        
        if response.status_code != 200:
            raise FHRAPIError(f"Download failed: {response.status_code}")
        
        if output_path is None:
            output_path = Path(filename)
        
        with open(output_path, 'wb') as f:
            f.write(response.content)
        
        return output_path
    
    def health_check(self) -> Dict[str, Any]:
        \"\"\"Check API health status.\"\"\"
        response = self.session.get(f"{self.base_url}/api/health")
        
        if response.status_code != 200:
            raise FHRAPIError(f"Health check failed: {response.status_code}")
        
        return response.json()

class FHRAPIError(Exception):
    \"\"\"Exception raised for FHR API errors.\"\"\"
    pass
```
        """

# Documentation website generator
class DocumentationWebsiteGenerator:
    """Generate static documentation website."""
    
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_website(
        self,
        code_docs: Dict[str, str],
        api_docs: Dict[str, Any],
        sdk_docs: Dict[str, str]
    ):
        """Generate complete documentation website."""
        # Generate index page
        self._generate_index_page()
        
        # Generate API documentation pages
        self._generate_api_pages(api_docs)
        
        # Generate code documentation pages
        self._generate_code_pages(code_docs)
        
        # Generate SDK documentation pages
        self._generate_sdk_pages(sdk_docs)
        
        # Generate navigation and assets
        self._generate_navigation()
        self._copy_assets()
    
    def _generate_index_page(self):
        """Generate main index page."""
        index_content = """
# FHR Documentation

Welcome to the FHR Attendance Analysis System documentation.

## Quick Links

- [API Reference](api/index.html) - REST API documentation
- [Code Documentation](code/index.html) - Internal code documentation  
- [SDK Documentation](sdk/index.html) - Client library documentation
- [Getting Started](getting-started.html) - Setup and basic usage
- [Enterprise Guide](enterprise.html) - Enterprise deployment guide

## System Overview

FHR is an enterprise-grade attendance analysis system designed for Taiwan businesses with flexible working hours. It provides:

- **Automated Analysis**: Process attendance records and identify issues
- **Multiple Output Formats**: Export results as Excel or CSV
- **Incremental Processing**: Analyze only new data efficiently
- **Holiday Integration**: Automatic Taiwan holiday detection
- **Enterprise Features**: Multi-tenant, audit logging, HRIS integration

## Architecture

The system consists of:

- **Core Analysis Engine**: Python-based attendance processing
- **REST API**: FastAPI web service for enterprise integration
- **Web Interface**: Browser-based file upload and analysis
- **CLI Tool**: Command-line interface for batch processing

[View detailed architecture documentation →](architecture.html)
        """
        
        with open(self.output_dir / "index.md", "w", encoding="utf-8") as f:
            f.write(index_content)
```

This documentation automation framework provides comprehensive tooling for automatically generating and maintaining up-to-date documentation across all aspects of the FHR system, from code-level documentation to API references and SDK guides.