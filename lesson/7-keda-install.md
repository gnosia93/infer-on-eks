## KEDA 설치 ##

```
helm repo add kedacore https://kedacore.github.io/charts
helm repo update

helm install keda kedacore/keda \
  --namespace keda --create-namespace \
  --version 2.21.1

kubectl get pods -n keda
```

[결과]
```
NAME                                              READY   STATUS    RESTARTS      AGE
keda-admission-webhooks-867bf9c74f-5fj6t          1/1     Running   0             63s
keda-operator-69cf66d857-bl4ss                    1/1     Running   1 (50s ago)   63s
keda-operator-metrics-apiserver-67fb5d96f-8jml7   1/1     Running   0             63s
```
* keda-operator: ScaledObject를 보고 HPA를 만듭니다.
* keda-operator-metrics-apiserver: HPA에 지표를 제공합니다.
* keda-admission-webhooks: 잘못된 ScaledObject를 거부합니다.

```
kubectl get apiservice v1beta1.external.metrics.k8s.io
```
[결과]
```
NAME                              SERVICE                                AVAILABLE   AGE
v1beta1.external.metrics.k8s.io   keda/keda-operator-metrics-apiserver   True        102s
```
* external.metrics.k8s.io는 클러스터에 하나만 등록할 수 있습니다. prometheus-adapter 같은 외부 지표 어댑터가 이미 있으면 KEDA와 충돌합니다. EKS 애드온 metrics-server는 metrics.k8s.io를 쓰므로 함께 써도 됩니다.


## Deployment 수정 ##

4장 매니페스트에서 두 곳을 고친 뒤 같은 kubectl apply를 다시 실행합니다.

매니페스트 안의 ${BUCKET}, ${AWS_REGION}이 치환되도록 이 환경 변수가 설정된 셸에서 실행합니다.
ScaledObject를 만들기 전, 레플리카가 1일 때 해야 레플리카 수가 흔들리지 않습니다.

```
spec:
  # replicas: 1                               # 삭제. 레플리카 수는 HPA가 정한다
  revisionHistoryLimit: 3
  ...
          args:
            ...
            - --port=8000
            - --shutdown-timeout=90           # 추가. SIGTERM을 받으면 처리 중인 요청을 최대 90초 기다린다
```
* replicas 삭제: 매니페스트에 replicas: 1이 남아 있으면 다시 apply할 때마다 레플리카가 1로 돌아갑니다. 그러면 HPA가 늘려 둔 서빙 파드가 내려갑니다.
* --shutdown-timeout 추가: 기본값 0이면 vLLM은 SIGTERM을 받자마자 처리 중인 요청을 중단합니다. 이 옵션은 스케일 인으로 파드가 지워질 때 응답이 중간에 끊기지 않게 합니다. preStop 20초와 합쳐 110초이므로 terminationGracePeriodSeconds(120초) 안에 들어옵니다.

args가 바뀌므로 롤링 업데이트가 한 번 일어납니다. 새 파드가 Ready가 될 때까지 약 7분 동안은 기존 파드가 요청을 받습니다.
