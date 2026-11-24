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

## ScaledObject 만들기 ##

### 스케일링 기준 ###
* 주 트리거 (동시 요청 수): 모든 파드의 running + waiting 합계를 1분 평균으로 봅니다.
  * 4장 측정에서 SLO(TTFT p99 1초, ITL p99 50ms)를 지키는 파드당 최대 동시성은 8이었습니다.
  * 새 파드가 요청을 받기까지 약 8분이 걸립니다(노드 준비 65초, 이미지 받기 176초, vLLM 기동 193초).
  * 그동안 버틸 여유를 두고 파드당 목표를 6으로 잡습니다.

* 보조 트리거 (KV 캐시 사용률): 모든 파드 사용률의 합계를 봅니다. 입력이 긴 요청이 몰리면 동시성이 낮아도 KV 캐시가 먼저 찹니다. 그래서 파드당 70%를 목표로 둡니다.

#### 두 트리거 모두 metricType: AverageValue를 씁니다. ####

* HPA가 정하는 레플리카 수는 ceil(쿼리 값 ÷ threshold)입니다. 예를 들어 KV 캐시 합계 0.8은 ceil(0.8 ÷ 0.7) = 2가 됩니다.
* 트리거가 여러 개면 가장 큰 값을 씁니다.
* 현재 값이 목표의 ±10% 안이면 바꾸지 않습니다(HPA 기본 tolerance). 그래서 경계 근처에서는 한 단계 늦게 바뀔 수 있습니다.


| 전체 동시 요청 수 (1분 평균) | 레플리카 |
| :--- | :--- |
| 6 이하 | 1 |
| 7 ~ 12 | 2 |
| 13 ~ 18 | 3 |
| 19 이상 | 4 (maxReplicaCount) |


