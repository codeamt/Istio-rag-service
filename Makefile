start-minikube:
	minikube start --driver=docker --cpus=4 --memory=6144 --kubernetes-version=1.28.0

install-istio:
	istioctl install --set profile=demo -y

microservice-container-build:
	docker build -t codeamt/istio-rag ./services/rag_service
	docker build -t codeamt/istio-scraper ./services/scraper_service

deploy:
	kubectl apply -f k8s/0-namespace.yaml
	kubectl apply -f k8s/1-istio-mtls.yaml
	kubectl apply -f k8s/2-vllm.yaml
	kubectl apply -f k8s/3-qdrant.yaml
	kubectl apply -f k8s/4-scraper-service.yaml
	kubectl apply -f k8s/5-rag-service.yaml
	kubectl apply -f k8s/6-observability.yaml
	kubectl apply -f k8s/7-network-policies.yaml
	kubectl apply -f k8s/8-virtual-services.yaml
	kubectl wait --for=condition=available --timeout=300s deployment/istio-ingressgateway -n istio-system
	@echo "Minikube is ready! Access RAG app at http://localhost:8080/api/query"

health-check:
	curl http://vllm:8000/health

log-check:
	kubectl logs deploy/scraper -n rag-system

# Docker Compose commands for local development
compose-up:
	docker-compose up -d

compose-down:
	docker-compose down

compose-logs:
	docker-compose logs -f

compose-ps:
	docker-compose ps

all: start-minikube install-istio microservice-container-build deploy health-check