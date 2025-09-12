#!/bin/bash
# SDK Generation Script
# Generates client SDKs from OpenAPI specification

set -e

# Configuration
API_URL="${API_URL:-http://localhost:8000}"
OPENAPI_SPEC_URL="${API_URL}/openapi.json"
PROJECT_NAME="gesahni-client"
VERSION="${VERSION:-$(git describe --tags --always 2>/dev/null || echo '0.0.0')}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if openapi-generator-cli is installed
check_dependencies() {
    log_info "Checking dependencies..."

    if ! command -v openapi-generator-cli &> /dev/null; then
        log_error "openapi-generator-cli is not installed"
        log_info "Install with: npm install -g @openapitools/openapi-generator-cli"
        exit 1
    fi

    if ! command -v curl &> /dev/null; then
        log_error "curl is not installed"
        exit 1
    fi

    log_success "Dependencies OK"
}

# Download OpenAPI spec
download_spec() {
    log_info "Downloading OpenAPI spec from ${OPENAPI_SPEC_URL}..."

    if ! curl -f -s "${OPENAPI_SPEC_URL}" -o openapi.json; then
        log_error "Failed to download OpenAPI spec from ${OPENAPI_SPEC_URL}"
        log_info "Make sure the API server is running at ${API_URL}"
        exit 1
    fi

    log_success "Downloaded OpenAPI spec"
}

# Generate JavaScript/TypeScript SDK
generate_js_sdk() {
    log_info "Generating JavaScript/TypeScript SDK..."

    mkdir -p sdks/js

    openapi-generator-cli generate \
        -i openapi.json \
        -g typescript-fetch \
        -o sdks/js \
        --additional-properties=npmName=@gesahni/client \
        --additional-properties=npmVersion="${VERSION}" \
        --additional-properties=supportsES6=true \
        --additional-properties=typescriptThreePlus=true \
        --additional-properties=withInterfaces=true \
        --additional-properties=withSeparateModelsAndApi=true

    # Create package.json for the SDK
    cat > sdks/js/package.json << EOF
{
  "name": "@gesahni/client",
  "version": "${VERSION}",
  "description": "GesahniV2 API Client SDK",
  "main": "dist/index.js",
  "types": "dist/index.d.ts",
  "scripts": {
    "build": "tsc",
    "test": "jest",
    "prepublishOnly": "npm run build"
  },
  "keywords": ["gesahni", "api", "client", "sdk"],
  "author": "Gesahni Team",
  "license": "MIT",
  "repository": {
    "type": "git",
    "url": "https://github.com/your-org/GesahniV2.git"
  },
  "dependencies": {
    "node-fetch": "^2.6.7"
  },
  "devDependencies": {
    "@types/node": "^20.0.0",
    "typescript": "^5.0.0",
    "jest": "^29.0.0",
    "@types/jest": "^29.0.0"
  }
}
EOF

    log_success "Generated JavaScript/TypeScript SDK in sdks/js/"
}

# Generate Python SDK
generate_python_sdk() {
    log_info "Generating Python SDK..."

    mkdir -p sdks/python

    openapi-generator-cli generate \
        -i openapi.json \
        -g python \
        -o sdks/python \
        --additional-properties=packageName=gesahni_client \
        --additional-properties=packageVersion="${VERSION}" \
        --additional-properties=projectName=GesahniClient

    # Create setup.py for the SDK
    cat > sdks/python/setup.py << EOF
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="gesahni-client",
    version="${VERSION}",
    author="Gesahni Team",
    author_email="team@gesahni.com",
    description="GesahniV2 API Client SDK",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/your-org/GesahniV2",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=[
        "requests>=2.25.0",
        "urllib3>=1.26.0",
        "python-dateutil>=2.8.0",
    ],
)
EOF

    log_success "Generated Python SDK in sdks/python/"
}

# Generate Go SDK
generate_go_sdk() {
    log_info "Generating Go SDK..."

    mkdir -p sdks/go

    openapi-generator-cli generate \
        -i openapi.json \
        -g go \
        -o sdks/go \
        --additional-properties=packageName=gesahni \
        --additional-properties=packageVersion="${VERSION}" \
        --additional-properties=isGoSubmodule=true

    # Create go.mod for the SDK
    cat > sdks/go/go.mod << EOF
module github.com/gesahni/go-client

go 1.19

require (
    github.com/stretchr/testify v1.8.1
    gopkg.in/yaml.v2 v2.4.0
)
EOF

    log_success "Generated Go SDK in sdks/go/"
}

# Generate all SDKs
generate_all_sdks() {
    log_info "Generating all SDKs..."

    download_spec
    generate_js_sdk
    generate_python_sdk
    generate_go_sdk

    log_success "All SDKs generated successfully!"
    log_info "Generated SDKs:"
    echo "  - JavaScript/TypeScript: sdks/js/"
    echo "  - Python: sdks/python/"
    echo "  - Go: sdks/go/"
}

# Publish SDKs to package registries
publish_sdks() {
    log_info "Publishing SDKs..."

    # JavaScript/TypeScript
    if [ -d "sdks/js" ]; then
        log_info "Publishing JavaScript SDK to npm..."
        cd sdks/js
        npm publish --access public
        cd ../..
        log_success "Published JavaScript SDK"
    fi

    # Python
    if [ -d "sdks/python" ]; then
        log_info "Publishing Python SDK to PyPI..."
        cd sdks/python
        python setup.py sdist bdist_wheel
        twine upload dist/*
        cd ../..
        log_success "Published Python SDK"
    fi

    # Go
    if [ -d "sdks/go" ]; then
        log_info "Go SDK ready for publishing (manual step required)"
        log_info "To publish Go SDK:"
        echo "  1. Create a GitHub repository: github.com/gesahni/go-client"
        echo "  2. Push the generated code to the repository"
        echo "  3. Users can install with: go get github.com/gesahni/go-client"
    fi
}

# Clean up generated files
clean() {
    log_info "Cleaning up generated SDKs..."
    rm -rf sdks/
    rm -f openapi.json
    log_success "Cleaned up"
}

# Main script logic
main() {
    case "${1:-generate}" in
        "generate")
            check_dependencies
            generate_all_sdks
            ;;
        "js")
            check_dependencies
            download_spec
            generate_js_sdk
            ;;
        "python")
            check_dependencies
            download_spec
            generate_python_sdk
            ;;
        "go")
            check_dependencies
            download_spec
            generate_go_sdk
            ;;
        "publish")
            publish_sdks
            ;;
        "clean")
            clean
            ;;
        "spec")
            download_spec
            log_info "OpenAPI spec downloaded to openapi.json"
            ;;
        *)
            echo "Usage: $0 [command]"
            echo "Commands:"
            echo "  generate  - Generate all SDKs (default)"
            echo "  js        - Generate only JavaScript/TypeScript SDK"
            echo "  python    - Generate only Python SDK"
            echo "  go        - Generate only Go SDK"
            echo "  spec      - Download OpenAPI spec only"
            echo "  publish   - Publish all generated SDKs"
            echo "  clean     - Clean up generated files"
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"
