## KEDA ##

아래 명령어로 KEDA 를 설치한다.
```
helm repo add kedacore https://kedacore.github.io/charts
helm repo update
helm install keda kedacore/keda --namespace keda --create-namespace
```

아래와 같이 ScaledObject 를 생성한다. ScaledObject 는 KEDA가 제공하는 CRD(Custom Resource Definition)로 "어떤 Deployment를 어떤 메트릭 기준으로 스케일링할지" 정의하는 리소스이다. ScaledObject를 만들면 KEDA가 알아서 HPA를 생성하고 관리하기 때문에 직접 HPA를 만들 필요 없다.
```
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: vllm-qwen-scaler
spec:
  scaleTargetRef:
    name: vllm-qwen
  minReplicaCount: 2
  maxReplicaCount: 8
  cooldownPeriod: 300          # 축소 전 5분 대기
  triggers:
    - type: prometheus
      metadata:
        serverAddress: http://prometheus-server.monitoring:9090
        query: sum(vllm:num_requests_waiting{namespace="default"})
        threshold: "10"
```
* Prometheus → KEDA (직접 연결) → HPA 자동 생성
