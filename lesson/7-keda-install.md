## KEDA 설치 ##

```
helm repo add kedacore https://kedacore.github.io/charts
helm repo update

helm install keda kedacore/keda \
  --namespace keda --create-namespace \
  --version 2.21.1

kubectl get pods -n keda
kubectl get apiservice v1beta1.external.metrics.k8s.io
```
다음 세 파드가 Running이고 APIService의 AVAILABLE이 True면 정상입니다.

keda-operator: ScaledObject를 보고 HPA를 만듭니다.
keda-operator-metrics-apiserver: HPA에 지표를 제공합니다.
keda-admission-webhooks: 잘못된 ScaledObject를 거부합니다.
external.metrics.k8s.io는 클러스터에 하나만 등록할 수 있습니다. prometheus-adapter 같은 외부 지표 어댑터가 이미 있으면 KEDA와 충돌합니다. EKS 애드온 metrics-server는 metrics.k8s.io를 쓰므로 함께 써도 됩니다.
