## Prometheus 설치 ##
kube-prometheus-stack 차트 하나로 다음 구성 요소를 함께 설치한다.

* Prometheus Operator
* Prometheus
* Grafana
* kube-state-metrics
* node-exporter

서비스는 모두 ClusterIP 로, 클러스터 밖에서는 접속할 수 없고, 필요할 때 kubectl port-forward 한다.

```
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

kubectl create namespace monitoring

# Grafana 관리자 비밀번호를 무작위로 만들어 시크릿에 넣는다 (차트 기본 비밀번호 prom-operator를 쓰지 않음)
kubectl create secret generic grafana-admin -n monitoring \
  --from-literal=admin-user=admin \
  --from-literal=admin-password="$(openssl rand -base64 18)"

cat > kps-values.yaml <<'EOF'
# EKS 컨트롤 플레인은 AWS가 관리하므로 아래 컴포넌트는 수집할 수 없다
kubeControllerManager:
  enabled: false
kubeScheduler:
  enabled: false
kubeEtcd:
  enabled: false

prometheus:
  prometheusSpec:
    # release 레이블이 없는 ServiceMonitor, PodMonitor, PrometheusRule도 모든 네임스페이스에서 찾는다
    serviceMonitorSelectorNilUsesHelmValues: false
    podMonitorSelectorNilUsesHelmValues: false
    ruleSelectorNilUsesHelmValues: false
    retention: 7d
    resources:
      requests:
        cpu: 500m
        memory: 2Gi
      limits:
        memory: 4Gi

grafana:
  admin:
    existingSecret: grafana-admin
    userKey: admin-user
    passwordKey: admin-password
EOF

helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --version 93.9.0 \
  -f kps-values.yaml

kubectl get pods -n monitoring
```
* ServiceMonitor 선택: serviceMonitorSelectorNilUsesHelmValues의 기본값은 true 이다. 이 상태에서는 release: kube-prometheus-stack 레이블이 붙은 ServiceMonitor만 수집하므로, false로 바꾼다.
* 데이터 보관: 데이터는 Prometheus 파드의 emptyDir에 저장되므로 오래 보관하려면 prometheusSpec.storageSpec으로 EBS 볼륨을 붙인다.
* GPU 노드 사용: GPU 노드에는 테인트가 있어서 node-exporter 같은 데몬셋 말고는 올라가지 않는다.


## vLLM 지표 수집 (ServiceMonitor) ##
vLLM은 API와 같은 8000 포트의 /metrics로 지표를 내보낸다. ServiceMonitor는 쿠버네티스 Service를 레이블로 찾고, 그 뒤의 파드들을 수집 대상으로 등록한다.
```
kubectl apply -f - <<'EOF'
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: gemma4-12b-vllm
  namespace: llm-serving
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: gemma4-12b-vllm    # 4장 Service의 레이블
  endpoints:
    - port: http                                  # Service 포트 이름 (번호가 아님)
      path: /metrics
      interval: 15s                               # 기본 30초를 15초로 줄여 스케일링 반응을 빠르게
      scrapeTimeout: 10s
EOF
```

아래 명령으로 수집이 되는지 확인한다. 
```
kubectl -n monitoring port-forward svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 &
PF_PID=$!

# 수집 대상 상태: health가 up이어야 한다
curl -s 'http://localhost:9090/api/v1/targets?state=active' | jq -r '
  .data.activeTargets[]
  | select(.labels.namespace == "llm-serving")
  | "\(.labels.pod)  \(.health)  \(.lastError)"'

# 스케일링에 쓸 지표
curl -s http://localhost:9090/api/v1/query \
  --data-urlencode 'query={namespace="llm-serving", __name__=~"vllm:(num_requests_running|num_requests_waiting|kv_cache_usage_perc)"}' \
  | jq -r '.data.result[] | "\(.metric.__name__)  \(.metric.pod)  \(.value[1])"'

kill $PF_PID
```

ServiceMonitor를 만들고 1분 정도 지나면 수집 대상이 보인다.

지표	뜻	쓰는 곳
vllm:num_requests_running	배치에 들어가 처리 중인 요청 수	주 트리거
vllm:num_requests_waiting	큐에서 기다리는 요청 수	주 트리거에 더함 (처리 용량을 넘는 수요)
vllm:kv_cache_usage_perc	KV 캐시 사용률 (1이 100%)	보조 트리거
모든 지표에 model_name 레이블이 붙습니다. 값은 --served-model-name으로 지정한 gemma-4-12b입니다.
Prometheus는 여기에 namespace, pod 레이블을 더합니다.
예전 버전의 vllm:gpu_cache_usage_perc는 vllm:kv_cache_usage_perc로 이름이 바뀌었습니다.

