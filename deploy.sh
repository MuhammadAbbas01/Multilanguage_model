#!/bin/bash

# Lingua Translate Deployment Script
# Supports Railway, Render, Fly.io, and Kubernetes

set -e

echo "🚀 Lingua Translate Deployment Script"
echo "======================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
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

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Deployment options
deploy_railway() {
    log_info "Deploying to Railway..."
    
    if ! command_exists railway; then
        log_error "Railway CLI not found. Install with: npm install -g @railway/cli"
        exit 1
    fi
    
    railway login
    railway up
    
    log_success "Deployed to Railway!"
}

deploy_render() {
    log_info "Deploying to Render..."
    log_info "Please connect your GitHub repo to Render manually"
    log_info "Use the render.yaml configuration file"
}

deploy_fly() {
    log_info "Deploying to Fly.io..."
    
    if ! command_exists flyctl; then
        log_error "Fly CLI not found. Install from: https://fly.io/docs/getting-started/installing-flyctl/"
        exit 1
    fi
    
    flyctl launch
    flyctl deploy
    
    log_success "Deployed to Fly.io!"
}

deploy_kubernetes() {
    log_info "Deploying to Kubernetes..."
    
    if ! command_exists kubectl; then
        log_error "kubectl not found. Please install Kubernetes CLI"
        exit 1
    fi
    
    # Apply all Kubernetes manifests
    kubectl apply -f k8s/
    
    # Wait for deployment
    kubectl rollout status deployment/lingua-translate
    
    log_success "Deployed to Kubernetes!"
}

build_docker() {
    log_info "Building Docker image..."
    
    if ! command_exists docker; then
        log_error "Docker not found. Please install Docker"
        exit 1
    fi
    
    docker build -t lingua-translate:latest .
    
    log_success "Docker image built successfully!"
}

# Main menu
show_menu() {
    echo ""
    echo "Select deployment option:"
    echo "1) Railway (Recommended for free tier)"
    echo "2) Render (Free web services)"  
    echo "3) Fly.io (Global edge deployment)"
    echo "4) Kubernetes (Production)"
    echo "5) Build Docker image only"
    echo "6) Exit"
    echo ""
}

# Main script
main() {
    # Check if we're in the right directory
    if [[ ! -f "main.py" ]]; then
        log_error "main.py not found. Please run this script from the project root directory."
        exit 1
    fi
    
    while true; do
        show_menu
        read -p "Enter your choice (1-6): " choice
        
        case $choice in
            1)
                deploy_railway
                break
                ;;
            2)
                deploy_render
                break
                ;;
            3)
                deploy_fly
                break
                ;;
            4)
                deploy_kubernetes
                break
                ;;
            5)
                build_docker
                break
                ;;
            6)
                log_info "Goodbye!"
                exit 0
                ;;
            *)
                log_error "Invalid option. Please choose 1-6."
                ;;
        esac
    done
}

# Run main function
main "$@"
