#!/bin/bash

# Enhanced Translation Service Deployment Script
# This script handles both Docker and Kubernetes deployment

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
DOCKER_IMAGE="your-dockerhub-username/lingua-translate"
VERSION="v2.1.0"
NAMESPACE="lingua-translate"
DOMAIN="translate-api.yourdomain.com"  # UPDATE THIS

# Functions
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

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        exit 1
    fi
    
    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed"
        exit 1
    fi
    
    # Check if we can connect to Kubernetes cluster
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster"
        exit 1
    fi
    
    log_success "Prerequisites check passed"
}

create_dockerfile() {
    log_info "Creating optimized Dockerfile..."
    
    cat > Dockerfile << 'EOF'
# Multi-stage Dockerfile for optimized production build
FROM python:3.11-slim as builder

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.11-slim

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy application code
COPY --chown=appuser:appuser . .

# Create necessary directories
RUN mkdir -p /app/logs /tmp && \
    chown -R appuser:appuser /app /tmp

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1

# Expose port
EXPOSE 5000

# Run application
CMD ["python", "main.py"]
EOF

    log_success "Dockerfile created"
}

create_requirements() {
    log_info "Creating requirements.txt..."
    
    cat > requirements.txt << 'EOF'
Flask==3.0.0
Werkzeug==3.0.1
structlog==23.2.0
prometheus-client==0.19.0
gunicorn==21.2.0
redis==5.0.1
transformers==4.35.2
torch==2.1.1
sentencepiece==0.1.99
protobuf==4.25.1
requests==2.31.0
urllib3==2.1.0
EOF

    log_success "requirements.txt created"
}

build_and_push_image() {
    log_info "Building Docker image..."
    
    # Build the image
    docker build -t ${DOCKER_IMAGE}:${VERSION} -t ${DOCKER_IMAGE}:latest .
    
    log_success "Docker image built successfully"
    
    # Push to registry
    log_info "Pushing Docker image to registry..."
    docker push ${DOCKER_IMAGE}:${VERSION}
    docker push ${DOCKER_IMAGE}:latest
    
    log_success "Docker image pushed successfully"
}

deploy_to_kubernetes() {
    log_info "Deploying to Kubernetes..."
    
    # Create namespace if it doesn't exist
    kubectl create namespace ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -
    
    # Apply the Kubernetes manifests
    log_info "Applying Kubernetes manifests..."
    
    # Update the deployment YAML with correct image
    sed -i "s|your-dockerhub-username/lingua-translate:latest|${DOCKER_IMAGE}:${VERSION}|g" deployment.yaml
    sed -i "s|translate-api.yourdomain.com|${DOMAIN}|g" deployment.yaml
    
    kubectl apply -f deployment.yaml
    
    log_success "Kubernetes manifests applied"
}

wait_for_deployment() {
    log_info "Waiting for deployment to be ready..."
    
    # Wait for deployment
    kubectl wait --for=condition=available --timeout=300s deployment/lingua-translate -n ${NAMESPACE}
    
    # Wait for pods to be ready
    kubectl wait --for=condition=ready --timeout=300s pods -l app=lingua-translate -n ${NAMESPACE}
    
    log_success "Deployment is ready"
}

run_tests() {
    log_info "Running deployment tests..."
    
    # Get service endpoint
    SERVICE_IP=$(kubectl get service lingua-translate-service -n ${NAMESPACE} -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
    
    if [ -z "$SERVICE_IP" ]; then
        log_warning "LoadBalancer IP not available yet, using port-forward for testing"
        kubectl port-forward -n ${NAMESPACE} service/lingua-translate-service 8080:80 &
        PF_PID=$!
        sleep 5
        SERVICE_URL="http://localhost:8080"
    else
        SERVICE_URL="http://${SERVICE_IP}"
    fi
    
    # Test health endpoint
    log_info "Testing health endpoint..."
    curl -f "${SERVICE_URL}/" || (log_error "Health check failed" && exit 1)
    
    # Test translation endpoints
    log_info "Testing translation endpoints..."
    
    # Test Spanish
    curl -X POST "${SERVICE_URL}/translate" \
        -H "Content-Type: application/json" \
        -d '{"text": "Hello world", "target_lang": "es"}' \
        -f || (log_error "Spanish translation test failed" && exit 1)
    
    # Test French
    curl -X POST "${SERVICE_URL}/translate" \
        -H "Content-Type: application/json" \
        -d '{"text": "Your premium subscription has been activated successfully", "target_lang": "fr"}' \
        -f || (log_error "French translation test failed" && exit 1)
    
    # Test Italian
    curl -X POST "${SERVICE_URL}/translate" \
        -H "Content-Type: application/json" \
        -d '{"text": "Welcome to our store", "target_lang": "it"}' \
        -f || (log_error "Italian translation test failed" && exit 1)
    
    # Test German
    curl -X POST "${SERVICE_URL}/translate" \
        -H "Content-Type: application/json" \
        -d '{"text": "Thank you", "target_lang": "de"}' \
        -f || (log_error "German translation test failed" && exit 1)
    
    # Test supported languages
    curl -f "${SERVICE_URL}/languages" || (log_error "Languages endpoint test failed" && exit 1)
    
    # Clean up port-forward if used
    if [ ! -z "$PF_PID" ]; then
        kill $PF_PID 2>/dev/null || true
    fi
    
    log_success "All tests passed"
}

show_deployment_info() {
    log_info "Deployment Information:"
    echo "=========================="
    
    echo "Namespace: ${NAMESPACE}"
    echo "Image: ${DOCKER_IMAGE}:${VERSION}"
    echo "Domain: ${DOMAIN}"
    echo ""
    
    echo "Pods:"
    kubectl get pods -n ${NAMESPACE}
    echo ""
    
    echo "Services:"
    kubectl get services -n ${NAMESPACE}
    echo ""
    
    echo "Ingress:"
    kubectl get ingress -n ${NAMESPACE}
    echo ""
    
    # Get external IP
    EXTERNAL_IP=$(kubectl get service lingua-translate-service -n ${NAMESPACE} -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
    if [ ! -z "$EXTERNAL_IP" ]; then
        echo "External IP: ${EXTERNAL_IP}"
        echo "API URL: http://${EXTERNAL_IP}"
    else
        log_warning "External IP not yet assigned. Use 'kubectl get services -n ${NAMESPACE}' to check later."
    fi
    
    echo ""
    echo "Useful commands:"
    echo "- View logs: kubectl logs -f deployment/lingua-translate -n ${NAMESPACE}"
    echo "- Scale deployment: kubectl scale deployment lingua-translate --replicas=5 -n ${NAMESPACE}"
    echo "- Port forward: kubectl port-forward -n ${NAMESPACE} service/lingua-translate-service 8080:80"
    echo "- Delete deployment: kubectl delete namespace ${NAMESPACE}"
}

# Main execution
main() {
    echo "=================================================="
    echo "Enhanced Translation Service Deployment Script"
    echo "Version: ${VERSION}"
    echo "=================================================="
    
    # Parse command line arguments
    case "${1:-all}" in
        "check")
            check_prerequisites
            ;;
        "build")
            check_prerequisites
            create_dockerfile
            create_requirements
            build_and_push_image
            ;;
        "deploy")
            check_prerequisites
            deploy_to_kubernetes
            wait_for_deployment
            ;;
        "test")
            check_prerequisites
            run_tests
            ;;
        "info")
            show_deployment_info
            ;;
        "all"|*)
            check_prerequisites
            create_dockerfile
            create_requirements
            build_and_push_image
            deploy_to_kubernetes
            wait_for_deployment
            run_tests
            show_deployment_info
            ;;
    esac
    
    log_success "Script completed successfully!"
}

# Run main function with all arguments
main "$@"