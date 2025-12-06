import sys
import os

# Add the services directories to the path so we can import the apps
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services', 'scraper_service'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services', 'rag_service'))
