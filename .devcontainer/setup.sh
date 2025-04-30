#!/bin/bash

# Install dependencies
apt-get update && apt-get install -y \
  curl \
  docker.io \
  conntrack \
  socat

# Start Docker 
systemctl enable docker && systemctl start docker 

# Install Minikube 
curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
install minikube-linux-amd64 /usr/local/bin/minikube

#Install kubectl and istioctl 
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
install kubectl /usr/local/bin/kubectl
curl -L https://istio.io/downloadIstio | sh -
mv istio-*/bin/istioctl /usr/local/bin/
