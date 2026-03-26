## Prometheus 커스텀 메트릭 구축 ##

어플리케이션 코드에서 커스텀 메트릭을 만들어서 Prometheus에 저장할 수 있다.
```
# Python 예시 (prometheus_client)
from prometheus_client import start_http_server, Gauge, Counter

# 메트릭 정의
TRAINING_LOSS = Gauge('training_loss', 'Current training loss')
TRAINING_STEP = Counter('training_step_total', 'Total training steps')
THROUGHPUT = Gauge('training_throughput_tokens_per_sec', 'Tokens per second')

# 메트릭 서버 시작 (:8000/metrics)
start_http_server(8000)

# 학습 루프에서 메트릭 업데이트
for step in range(total_steps):
    start = time.time()
    loss = train_one_step(batch)
    elapsed = time.time() - start
    
    # 배치 내 총 토큰 수
    tokens_in_batch = batch_size * sequence_length 
    # tokens/sec 계산
    tokens_per_sec = tokens_in_batch / elapsed  # 예: 131072 / 0.085 = 1,541,906
    
    TRAINING_LOSS.set(loss)
    TRAINING_STEP.inc()
    THROUGHPUT.set(tokens_per_sec)
```
```
# Prometheus가 스크래핑하면
curl localhost:8000/metrics
# training_loss 2.34
# training_step_total 5000
# training_throughput_tokens_per_sec 1520
```

#### 메트릭 타입 ####
![](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/images/prometheus-custom-metrics.png)
학습 모니터링에서는 Gauge(loss, throughput)와 Counter(step)를 주로 사용한다.

### 학습 throughput(tokens/sec) ###
"GPU를 얼마나 효율적으로 쓰고 있는가" 를 나타낸다. 예를 들어
```
정상: 1.5M tokens/sec (일정하게 유지)
문제: 1.5M → 0.8M 으로 떨어짐
  → 데이터 로딩 병목? 네트워크 병목? 스로틀링? 등이 그 원인일 수 있다.
```
AI 클러스터에서 GPU 사용률(sm)만으로는 학습이 정상적으로 이뤄지는지 판단하기에는 어려운 점이 있다. 
```
sm 98% + throughput 1.5M → 정상
sm 98% + throughput 0.8M → 스로틀링 (pclk 떨어진 상태로 열심히 돌고 있음)
sm 60% + throughput 0.8M → 데이터 로딩 병목
```
throughput이 학습 효율의 최종 지표이고, 이게 떨어지면 sm, pclk, 데이터 로딩을 순서대로 확인한다.

잡 로그에 step 시간이 찍히는 경우 커스텀 메트릭없이 훈련 효율을 측정할 수 있으나 대규모 AI 클러스터를 운영하는 운영자 입장에서는 이를 구축하는게 클러스터 관리면에서 좋다.
```
Step 100: loss=2.34, time=0.085s  → 131072/0.085 = 1.5M tokens/sec
Step 200: loss=2.12, time=0.150s  → 131072/0.150 = 0.87M tokens/sec ← 느려짐
```
>[!NOTE]
>Prometheus 메트릭은 메모리에 값만 저장해두고, Prometheus Scraper 가 15초마다 한 번 HTTP로 가져가는 구조라서 부하가 거의 없다.

## LOKI ##
Loki는 Grafana Labs가 만든 로그 수집/검색 시스템으로, "Prometheus의 로그 버전"이라고 불린다. 각 노드에 설치된 에이전트(Alloy/Promtail)가 syslog, 잡 로그, 커널 로그 등을 수집하고 라벨을 붙여서 Loki 서버로 전송하면, Loki는 라벨만 인덱싱하고 로그 본문은 압축 저장한다. 검색은 LogQL이라는 쿼리 언어를 사용하며, Grafana와 네이티브로 통합되어 Prometheus 메트릭과 Loki 로그를 같은 대시보드에서 시간축으로 겹쳐볼 수 있다. ELK(Elasticsearch) 대비 최대 강점은 비용인데, Elasticsearch는 로그 본문 전체를 인덱싱해서 디스크와 메모리를 많이 소비하는 반면, Loki는 라벨만 인덱싱하므로 대규모 클러스터에서 운영 비용이 훨씬 저렴하다. GPU 클러스터 1000대 규모에서 로그가 폭발적으로 늘어나는 환경에서는 Loki가 현실적인 선택이다.

### 구성요소 ###
* Distributor  → 로그 수신 + 샤딩(라벨 기반으로 Ingester에 분배)
* Ingester     → 로그 저장 (여러 인스턴스로 구성하여 분산), 로그는 메모리 버퍼링후 일정량 쌓이면 스토어에 flush   
* Querier      → LogQL 쿼리 처리, 인덱스에서 라벨 검색 → 청크 읽기 
* Compactor    → 오래된 청크 압축/병합/삭제 
* Store        → S3/GCS 같은 오브젝트 스토리지에 영구 저장 / 라벨 → 인덱스, 본문 → 압축 청크

![](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/images/loki-arch.png)
* 로그 수집 파이프라인 : Alloy -> Loki -> Grafana


### LogQL 예시 ###
그라파나 대시보드에서 LogQL을 이용하여 로그를 조회한다.
```
# 특정 노드의 Xid 에러
{node="gpu-node-05"} |= "Xid"

# OOM kill 로그
{job="syslog"} |= "Out of memory"

# 특정 잡의 NCCL 에러
{job="slurm", jobid="12345"} |= "NCCL WARN"

# 에러 로그
{node=~"gpu-node-.*"} |= "error" | logfmt
```

## 프로메테우스 샤딩 ##
아래는 샤딩 관련 사이징 예시이다. 정확한 값은 측정이 필요하다.
```
DCGM Exporter: GPU당 약 50~100개 메트릭
Node Exporter: 노드당 약 500~1000개 메트릭
스크래핑 주기: 15초

노드당 메트릭 수 (8 GPU):
  DCGM: 8 GPU × 100 = 800
  Node: 1000
  합계: ~1,800 메트릭/노드
```

단일 Prometheus 한계: 약 100만~200만 active time series
* 100노드 (800 GPU):  ~180,000 시리즈 → 여유
* 500노드 (4,000 GPU): ~900,000 시리즈 → 한계 근접
* 1000노드 (8,000 GPU): ~1,800,000 시리즈 → Thanos 필요

>[!NOTE]
>대략 m5.4xlarge (64GB) 기준으로 500노드(GPU 4,000장) 정도가 단일 Prometheus의 한계로, 그 이상이면 Thanos나 Mimir로 샤딩이 필요하다.
>Prometheus 병목은 메모리로, active time series를 전부 메모리에 올려놓는다. 메모리가 충분하고 DISK 성능이 받쳐준다면 단일 인스턴스로도 수천대의 노드를 커버할 수 있다.
>단, 성능 테스트 후 구성해야 한다.

