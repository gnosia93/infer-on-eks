### LWS 설치 ###
```
# 최신 릴리스 버전 확인 후 사용 (예: v0.7.0)
VERSION=v0.7.0
kubectl apply --server-side -f \
  https://github.com/kubernetes-sigs/lws/releases/download/${VERSION}/manifests.yaml

kubectl -n lws-system rollout status deploy/lws-controller-manager
```

### 1. HF 토큰 시크릿 (게이트 모델용) ###
```
kubectl create namespace llm
kubectl -n llm create secret generic hf-token \
  --from-literal=token="<YOUR_HF_TOKEN>"
```

### 2. LeaderWorkerSet 매니페스트 (현재: 1B / Graviton CPU) ###
```

```


## 레퍼런스 ##

* https://aws.github.io/graviton/machinelearning/vllm.html 
