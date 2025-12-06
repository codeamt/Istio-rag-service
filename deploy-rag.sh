#!/bin/bash

# Apply Kubernetes Configs 
kubectl apply -f k8s/0-namespace.yaml
kubectl apply -f k8s/1-istio-mtls.yaml
kubectl apply -f k8s/2-vllm.yaml
kubectl apply -f k8s/3-qdrant.yaml
kubectl apply -f k8s/7-network-policies.yaml
kubectl apply -f k8s/8-virtual-services.yaml

# Build and deploy Python services 
docker build -t rag-service ./services/rag_service
docker build -t scraper-service ./services/scraper_service
kubectl apply -f k8s/4-scraper-service.yaml 
kubectl apply -f k8s/5-rag-service.yaml 

#Initialize Qdrant collection 
kubectl exec -it deploy/qdrant -- curl -X PUT "http://localhost:6333/collections/posts" -H "Content-Type: application/json" -d '{
    "name": "posts", 
    "vectors": {
        "size": 384,
        "distance": "Cosine"
    }
}

# Logging
echo "Deployment complete! access endpoints:"
echo "- RAG API: http://localhost:8080/api/query"
echo "- Scraper: http://localhost:8080/api/scrape"