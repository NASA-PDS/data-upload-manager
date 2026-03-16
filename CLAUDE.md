# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PDS Data Upload Manager (DUM) is a data ingress system for NASA's Planetary Data System that enables data providers to upload data deliveries to the Planetary Data Cloud (AWS S3). The system consists of:

- **Client**: Python CLI (`pds-ingress-client`) that performs file indexing, manifest generation, batch ingress requests, and S3 uploads
- **Service**: AWS Lambda functions that handle ingress requests, mapping local file paths to S3 destinations
- **Infrastructure**: Terraform modules for deploying API Gateway, Lambda functions, Cognito authentication, and SQS queues

## Development Commands

### Setup
```bash
# Install in editable mode with dev dependencies
pip install --editable '.[dev]'

# Configure pre-commit hooks
pre-commit install && pre-commit install -t pre-push
```

### Testing
```bash
# Run all tests
pytest

# Run tests with coverage
pytest --cov

# Run specific test file
pytest tests/pds/ingress/util/test_path_util.py

# Run tests in parallel
pytest -n auto
```

### Linting
```bash
# Run all linters (black, flake8, mypy, etc.)
tox -e lint

# Run black formatter
black src tests

# Run flake8
flake8 src

# Run pre-commit hooks manually
pre-commit run --all-files
```

### Build and Documentation
```bash
# Run full build (tests + linting + docs)
tox

# Build documentation only
sphinx-build -b html docs/source docs/build

# Test specific Python version
tox -e py312
tox -e py313
```

### Deployment
```bash
# Deploy to AWS
cd terraform/
terraform init
terraform apply
```

### Client Usage
```bash
# Run ingress client
pds-ingress-client -c <config path> -n <PDS node ID> -- <ingress path> [...]

# Run status client
pds-status-client --help
```

## Architecture

### Client-Side Architecture

The client (`pds_ingress_client.py`) executes a 5-step workflow:

1. **Indexing**: Recursively resolve input paths to determine full file set
2. **Manifest Generation**: Create manifest with MD5 checksums for each file (can be cached via `--manifest-path`)
3. **Batch Ingress Requesting**: Submit batch requests to DUM Ingress Service
4. **S3 Upload**: Parallel batch uploads to S3 using multipart uploads for large files
5. **Reporting**: Generate summary and detailed JSON reports

Key implementation details:
- Uses `joblib` with shared memory backend for parallelization (`PARALLEL` global)
- Implements bearer token authentication with periodic refresh via `sched.scheduler` (`REFRESH_SCHEDULER`)
- Progress tracking via `tqdm` progress bars for paths, manifests, batches, and uploads
- Batch size and thread count are configurable (default: `--num-threads` for parallel batches)
- Supports dry-run mode and force-overwrite options

### Service-Side Architecture

The Lambda service (`pds_ingress_app.py` and `pds_status_app.py`) handles:

**Ingress Service (`pds_ingress_app.py`)**:
- Receives batch ingress requests via API Gateway
- Maps local file paths to S3 destinations using configurable bucket mappings
- Handles single-part uploads (<5GB) and initiates multipart uploads (>5GB)
- Returns presigned S3 URLs for client-side uploads
- Uses environment variables for bucket configuration and endpoint URLs (for LocalStack testing)

**Status Service (`pds_status_app.py`)**:
- Processes status check requests via SQS queue
- Tracks upload completion and multipart upload status
- Monitors file integrity in S3

### Authentication Flow

- Uses AWS Cognito for authentication
- Lambda authorizer (`src/pds/ingress/authorizer/`) validates JWT access tokens
- Node.js-based authorizer using `aws-jwt-verify` library
- Supports multiple client IDs and user pools
- Client acquires and refreshes bearer tokens automatically

### Infrastructure Components

Terraform modules in `terraform/modules/`:
- **lambda/service**: Ingress and status Lambda functions
- **lambda/authorizer**: JWT token validation Lambda
- **api_gateway**: REST API with authorizer integration
- **cognito**: User pool and client configuration
- **sqs**: Status tracking queue

## Code Structure

```
src/pds/ingress/
├── client/              # Client-side scripts
│   ├── pds_ingress_client.py      # Main ingress client
│   ├── pds_status_client.py       # Status checking client
│   ├── abort_multipart_uploads.py # Cleanup utility
│   ├── inventory_generator.py     # S3 inventory tool
│   └── s3_to_s3_copy.py          # S3 copy utility
├── service/             # Lambda service implementations
│   ├── pds_ingress_app.py        # Ingress request handler
│   ├── pds_status_app.py         # Status tracking handler
│   ├── sync_s3_metadata.py       # Metadata sync utility
│   └── config/                   # Service configuration
├── authorizer/          # JWT authorizer (Node.js)
│   ├── index.js         # Token validation logic
│   └── package.json
└── util/                # Shared utilities
    ├── auth_util.py     # Cognito authentication
    ├── backoff_util.py  # Retry/backoff logic
    ├── config_util.py   # Configuration parsing
    ├── hash_util.py     # MD5 checksum generation
    ├── log_util.py      # Logging configuration
    ├── node_util.py     # PDS node ID handling
    ├── path_util.py     # Path manipulation
    ├── progress_util.py # Progress bar management
    └── report_util.py   # Manifest and report generation
```

### Important Implementation Notes

- **Import Handling**: Service code uses try/except for imports to support both AWS Lambda deployment (absolute imports) and unit testing (relative imports)
- **Manifest Caching**: Manifest files act as a cache across executions - reuse via `--manifest-path` to avoid re-hashing unchanged files
- **S3 Endpoints**: Service supports custom S3 endpoints via `ENDPOINT_URL` environment variable for LocalStack testing
- **Parallel Execution**: Client uses `joblib.Parallel` with `require="sharedmem"` for batch processing - threads share memory for manifest and summary tables
- **Progress Bars**: Complex progress bar management with batch-specific bars that are acquired/released from a pool

## Configuration

### Client Configuration
INI file format with sections for:
- Service endpoints and authentication
- Batch sizes
- Logging configuration
- Node-specific settings

### Service Configuration
Environment variables control:
- `LOG_LEVEL`: Logging verbosity
- `ENDPOINT_URL`: Custom S3 endpoint (for testing)
- `VERSION_LOCATION` / `VERSION_FILE`: Version file location in Lambda
- Cognito pool IDs and client IDs (for authorizer)

## Testing Strategy

- **Unit Tests**: `tests/pds/ingress/util/` - utilities and core logic
- **Integration Tests**: `integration/pds/ingress/` - full workflow tests against LocalStack
- **Pre-commit Hooks**: Run tests on push, linters on commit
- **Coverage**: Configured to omit `__init__.py` files

### Running Integration Tests

Integration tests require LocalStack:
1. Start LocalStack with appropriate services (S3, Lambda, API Gateway, Cognito, SQS)
2. Run setup scripts: `integration/scripts/create_localstack_iam_roles.sh`
3. Use templates in `integration/config/` for configuration
4. Execute: `pytest integration/`

## Python Version Compatibility

- **Minimum**: Python 3.12
- **Supported**: Python 3.12, 3.13
- Recent work focused on Python 3.12 compatibility (see feature branch: `feature/python-3.12-compatibility`)

## Code Style

- **Line Length**: 120 characters (black and flake8 configured)
- **Import Order**: Enforced by `reorder-python-imports` pre-commit hook
- **Docstring Format**: NumPy-style docstrings
- **Type Hints**: Partial typing with mypy checks (currently commented out in pre-commit)
