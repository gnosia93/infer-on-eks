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

### tokens/sec 의미 ###
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


#### 메트릭 타입 ####
![](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/images/prometheus-custom-metrics.png)
학습 모니터링에서는 Gauge(loss, throughput)와 Counter(step)를 주로 사용한다.


