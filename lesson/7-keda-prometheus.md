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
