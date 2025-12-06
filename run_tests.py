#!/usr/bin/env python3
"""
Test runner script for the Istio RAG Service.
"""
import subprocess
import sys
import os

def run_tests():
    """Run all tests for the project."""
    print("Running tests for Istio RAG Service...")
    
    # Change to the project root directory
    project_root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_root)
    
    # Run tests for both services
    try:
        # Run scraper service tests
        print("\nRunning scraper service tests...")
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            "tests/test_scraper_service.py", 
            "-v", "--tb=short"
        ], cwd=project_root)
        
        if result.returncode != 0:
            print("Scraper service tests failed!")
            return False
            
        # Run RAG service tests
        print("\nRunning RAG service tests...")
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            "tests/test_rag_service.py", 
            "-v", "--tb=short"
        ], cwd=project_root)
        
        if result.returncode != 0:
            print("RAG service tests failed!")
            return False
            
        print("\nAll tests passed successfully!")
        return True
        
    except Exception as e:
        print(f"Error running tests: {e}")
        return False

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
