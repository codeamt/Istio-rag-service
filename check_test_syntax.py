#!/usr/bin/env python3
"""
Syntax checker for test files.
"""
import ast
import os
import sys

def check_syntax(file_path):
    """Check syntax of a Python file."""
    try:
        with open(file_path, 'r') as f:
            source = f.read()
        ast.parse(source)
        print(f"✓ {file_path} - Syntax OK")
        return True
    except SyntaxError as e:
        print(f"✗ {file_path} - Syntax Error: {e}")
        return False
    except Exception as e:
        print(f"✗ {file_path} - Error: {e}")
        return False

def main():
    """Check syntax of all test files."""
    test_dir = os.path.join(os.path.dirname(__file__), 'tests')
    if not os.path.exists(test_dir):
        print(f"Test directory not found: {test_dir}")
        return False
    
    success = True
    
    # Check test files
    for filename in os.listdir(test_dir):
        if filename.startswith('test_') and filename.endswith('.py'):
            file_path = os.path.join(test_dir, filename)
            if not check_syntax(file_path):
                success = False
    
    # Check test runner
    runner_path = os.path.join(os.path.dirname(__file__), 'run_tests.py')
    if os.path.exists(runner_path):
        if not check_syntax(runner_path):
            success = False
    
    # Check conftest
    conftest_path = os.path.join(test_dir, 'conftest.py')
    if os.path.exists(conftest_path):
        if not check_syntax(conftest_path):
            success = False
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
