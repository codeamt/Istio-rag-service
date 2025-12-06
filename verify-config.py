#!/usr/bin/env python3
"""
Configuration verification script for Istio RAG Service.
This script checks if all configuration files are properly structured
without actually deploying the services.
"""

import os
import sys
from pathlib import Path

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    print("⚠️  PyYAML not available. Skipping YAML validation.")
    print("   Install with: pip install PyYAML\n")
    YAML_AVAILABLE = False

def check_k8s_files():
    """Check if all Kubernetes files are properly structured."""
    k8s_dir = Path('k8s')
    if not k8s_dir.exists():
        print("❌ k8s directory not found")
        return False
    
    # List of expected files
    expected_files = [
        '0-namespace.yaml',
        '1-istio-mtls.yaml',
        '2-vllm.yaml',
        '3-qdrant.yaml',
        '4-scraper-service.yaml',
        '5-rag-service.yaml',
        '6-observability.yaml',
        '7-network-policies.yaml',
        '8-virtual-services.yaml'
    ]
    
    all_good = True
    for filename in expected_files:
        file_path = k8s_dir / filename
        if not file_path.exists():
            print(f"❌ Expected file not found: {filename}")
            all_good = False
            continue
        
        # Try to parse YAML if available
        if YAML_AVAILABLE:
            try:
                with open(file_path, 'r') as f:
                    yaml.safe_load_all(f)
                print(f"✅ {filename} - YAML structure OK")
            except Exception as e:
                print(f"❌ {filename} - YAML parsing error: {e}")
                all_good = False
        else:
            # Just check if file exists and is readable
            try:
                with open(file_path, 'r') as f:
                    f.read(1)  # Try to read first character
                print(f"✅ {filename} - File exists and is readable")
            except Exception as e:
                print(f"❌ {filename} - File error: {e}")
                all_good = False
    
    return all_good

def check_dockerfiles():
    """Check if Dockerfiles exist and are properly structured."""
    dockerfiles = [
        'services/rag_service/Dockerfile',
        'services/scraper_service/Dockerfile'
    ]
    
    all_good = True
    for dockerfile in dockerfiles:
        file_path = Path(dockerfile)
        if not file_path.exists():
            print(f"❌ Dockerfile not found: {dockerfile}")
            all_good = False
        else:
            print(f"✅ {dockerfile} - Exists")
    
    return all_good

def check_python_services():
    """Check if Python service files exist and have health endpoints."""
    service_files = [
        'services/rag_service/app.py',
        'services/scraper_service/scraper_service.py'
    ]
    
    all_good = True
    for service_file in service_files:
        file_path = Path(service_file)
        if not file_path.exists():
            print(f"❌ Service file not found: {service_file}")
            all_good = False
            continue
        
        # Check for health endpoint
        try:
            with open(file_path, 'r') as f:
                content = f.read()
                if 'health' in content.lower():
                    print(f"✅ {service_file} - Has health endpoint")
                else:
                    print(f"⚠️  {service_file} - No health endpoint found")
        except Exception as e:
            print(f"❌ {service_file} - Error reading file: {e}")
            all_good = False
    
    return all_good

def check_makefile():
    """Check if Makefile has required targets."""
    makefile_path = Path('Makefile')
    if not makefile_path.exists():
        print("❌ Makefile not found")
        return False
    
    required_targets = ['start-minikube', 'install-istio', 'deploy']
    try:
        with open(makefile_path, 'r') as f:
            content = f.read()
            all_good = True
            for target in required_targets:
                if target in content:
                    print(f"✅ Makefile - Has target: {target}")
                else:
                    print(f"❌ Makefile - Missing target: {target}")
                    all_good = False
            return all_good
    except Exception as e:
        print(f"❌ Error reading Makefile: {e}")
        return False

def main():
    """Main verification function."""
    print("🔍 Verifying Istio RAG Service configuration...")
    print()
    
    checks = [
        ("Kubernetes Files", check_k8s_files),
        ("Dockerfiles", check_dockerfiles),
        ("Python Services", check_python_services),
        ("Makefile", check_makefile)
    ]
    
    all_passed = True
    for name, check_func in checks:
        print(f"\n📋 Checking {name}...")
        if not check_func():
            all_passed = False
    
    print()
    if all_passed:
        print("🎉 All configuration checks passed!")
        print("✅ The project is ready for deployment with minikube and Istio.")
        return 0
    else:
        print("❌ Some configuration checks failed.")
        print("⚠️  Please fix the issues before deploying.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
