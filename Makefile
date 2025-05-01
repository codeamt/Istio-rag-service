start-minikube:
	minikube start --driver=docker --cpus=4 --memory=8192 --kubernetes-version=1.27.0

install-istio:
	istioctl install --set profile=demo -y

microservice-container-build:
	docker build -t codeamt/istio-rag ./services/rag_service
	docker build -t codeamt/istio-scraper ./services/scraper_service

deploy:
	kubectl apply -f ./k8s/
	kubectl wait --for=condition=available --timeout=300s deployment/istio-ingressgateway -n istio-system
	@echo "Minikube is ready! Access RAG app at http://localhost:8080/api/query"

health-check:
	curl http://vllm:8000/health

log-check:
	kubectl logs deploy/scraper -n rag-system

all: start-minikube install-istio microservice-container-build deploy health-check