## vLLM 인퍼런스 ##

### vLLM 배포하기 ###
Qwen2.5-27B 모델을 g6e.12xlarge (L40S 48GB * 4EA, TP=4) 설정으로 2개의 파드로 구성한다.
[g6e.12xlarge](https://aws.amazon.com/ko/ec2/instance-types/g6e/) 인스턴스는 2대가 필요하다.

* https://raw.githubusercontent.com/gnosia93/eks-agentic-ai/refs/heads/main/code/yaml/vllm-qwen.yaml
```bash
curl -o vllm-qwen.yaml https://raw.githubusercontent.com/gnosia93/eks-agentic-ai/refs/heads/main/code/yaml/vllm-qwen.yaml
kubectl -f vllm-qwen.yaml
```
vLLM은 시작 시 먼저 모델 가중치를 GPU 메모리에 로드하고, gpu-memory-utilization 설정값에 따라 사용 가능한 전체 메모리 범위를 결정한다. 그런 다음 모델 가중치와 내부 버퍼를 제외한 나머지 메모리를 KV Cache로 자동 할당하며, 이 KV Cache 크기와 max-model-len을 기반으로 동시에 처리할 수 있는 최대 요청 수를 자동으로 결정한다.
모델 가중치 로드 → 남은 메모리 계산 (gpu-memory-utilization 기준) → 남은 메모리를 KV Cache로 자동 할당 → KV Cache 크기 + max-model-len 기반으로 동시 처리 가능 수 자동 결정

### vLLM 파라미터 ###
* --model                     사용모델
* --tensor-parallel-size      GPU 갯수
* --max-model-len             최대 시퀀스 길이
* --gpu-memory-utilization    GPU 메모리 상용률(90% 권장)
   - CUDA 커널 실행 오버헤드, Activation 임시 버퍼, Tensor 연산 중간 결과물, NCCL 통신 버퍼 (TP 사용시)

### vLLM 추론 최적화 ###
vLLM은 아래 세 가지 최적화를 기본 내장하고 있어 별도 설정 없이 자동 적용된다.

#### KV Cache 최적화 (PagedAttention) ####
Transformer는 토큰을 생성할 때마다 이전 토큰들의 Key/Value 텐서를 참조해야 한다. 이를 KV Cache라 하며, 시퀀스가 길어질수록 GPU 메모리를 많이 차지한다.
기존 방식은 요청마다 max-model-len 크기의 연속 메모리를 미리 할당했다. 실제로 10토큰만 생성해도 4096토큰분의 메모리를 점유하므로 낭비가 심하다.
vLLM의 PagedAttention은 OS의 가상 메모리 페이징에서 착안한 방식으로, KV Cache를 고정 크기 블록(페이지) 단위로 나누어 필요할 때만 할당한다.
```
기존 방식:
요청 A: [████████████████████░░░░░░░░░░░░] ←  max-model-len 토큰 할당, 실제 1200 토큰 사용
요청 B: [██████░░░░░░░░░░░░░░░░░░░░░░░░░░] ←  max-model-len 토큰 할당, 실제 400 토큰 사용
→ 메모리 낭비 심함

PagedAttention:
요청 A: [블록1][블록2][블록3] ← 필요한 만큼만 블록 할당
요청 B: [블록4] ← 필요한 만큼만 블록 할당
→ 남은 블록은 다른 요청이 사용 가능
```
이를 통해 동일 GPU 메모리에서 더 많은 요청을 동시에 처리할 수 있다. --gpu-memory-utilization과 --max-model-len 파라미터가 전체 KV Cache 풀 크기를 결정한다.

#### Continuous Batching ####
기존 Static Batching은 배치 안의 모든 요청이 완료될 때까지 기다린 후 다음 배치를 처리한다. 짧은 요청이 먼저 끝나도 긴 요청이 끝날 때까지 GPU가 유휴 상태가 된다.
vLLM은 매 토큰 생성 스텝마다 배치를 재구성하여 완료된 요청을 빼고 대기 중인 요청을 즉시 투입한다. 이를 통해 GPU 활용률과 전체 처리량(throughput)이 크게 향상된다.

#### Prefill/Decode 분리 ####
LLM 추론은 두 단계로 나뉜다.
* Prefill: 입력 프롬프트의 모든 토큰을 한 번에 처리하여 KV Cache를 생성하는 단계. 행렬 연산이 크고 GPU 연산(compute)이 병목이다.
* Decode: KV Cache를 참조하며 토큰을 하나씩 생성하는 단계. 연산량은 적지만 매 스텝마다 GPU 메모리를 읽어야 하므로 메모리 대역폭(memory bandwidth)이 병목이다.
두 단계의 리소스 특성이 다르기 때문에, 같은 GPU에서 Prefill과 Decode가 섞이면 서로 간섭이 발생한다. 긴 프롬프트의 Prefill이 실행되면 Decode 중인 요청의 TPOT(Time per Output Token)이 튀는 현상이 생긴다. vLLM은 내부 스케줄러에서 Prefill과 Decode의 우선순위를 조절하여 이 간섭을 최소화한다.

### 테스트 하기 ###
```bash
# 클러스터 내부에서 테스트 (임시 파드)
kubectl run test --rm -it --image=curlimages/curl -- \
  curl http://vllm-qwen-svc/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 50
  }'
```
또는
```bash
# 터미널 1: 포트 포워딩
kubectl port-forward svc/vllm-qwen-svc 8080:80

# 터미널 2: 테스트
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 50
  }'
```

### 성능 밴치마크 ###
```bash
kubectl get pods

# vLLM 벤치마크 (파드 안에서 실행)
kubectl exec -it <vllm-pod-name> -- python -m vllm.entrypoints.openai.api_server &

python -m vllm.entrypoints.openai.bench_serving \
  --backend openai \
  --base-url http://localhost:8000 \
  --model qwen \
  --num-prompts 100 \
  --request-rate 10
```

### Speculative Decoding 적용 ###
Speculative Decoding은 작은 모델(draft)이 먼저 여러 토큰을 추측 생성하고, 큰 모델(target)이 한 번에 검증하는 방식으로 추론 속도를 높이는 방식이다.

* Target 모델: Qwen2.5-27B (기존 배포 모델)
* Draft 모델: Qwen2.5-3B (같은 계열의 작은 모델, 추측 적중률이 높음)
기존 vllm-qwen.yaml 에서 args 부분만 수정한다.
```
args:
  - "--model=Qwen/Qwen2.5-Coder-27B-Instruct"
  - "--tensor-parallel-size=4"
  - "--max-model-len=4096"
  - "--gpu-memory-utilization=0.90"
  - "--speculative-model=Qwen/Qwen2.5-Coder-3B-Instruct"
  - "--num-speculative-tokens=5"
```

* 파라미터	설명
 * --speculative-model	추측 생성에 사용할 draft 모델
 * --num-speculative-tokens	draft 모델이 한 번에 추측할 토큰 수 (5가 일반적)
draft 모델(3B)은 target 모델(27B)과 같은 GPU 메모리에 함께 로드된다. 3B 모델은 약 6GB 정도 차지하므로 L40S 48GB × 4 구성에서 메모리 여유가 충분하다.

#### 성능 비교 벤치마크 ####
Speculative Decoding 적용 후 동일한 벤치마크를 실행하여 베이스라인과 비교한다.

```
kubectl exec -it <vllm-pod-name> -- \
  python -m vllm.entrypoints.openai.bench_serving \
    --backend openai \
    --base-url http://localhost:8000 \
    --model qwen \
    --num-prompts 100 \
    --request-rate 10
```
TTFT (Time to First Token), TPOT (Time per Output Token), Throughput (tokens/sec), Request Latency (p50/p99) 을 baseline 과 비교한다.

TPOT와 Throughput에서 가장 큰 차이가 나타난다. 일반적으로 1.5~2.5배 속도 향상을 기대할 수 있으며, 코드 생성처럼 정형화된 출력에서 효과가 더 크다.

num-speculative-tokens는 너무 높이면 draft 모델의 추측이 틀릴 확률이 올라가서 오히려 느려질수 있다. 5가 무난한 시작점이고, 벤치마크 결과 보면서 3~7 사이에서 조절한다.
