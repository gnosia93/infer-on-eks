## 멀티 노드 인퍼런스 최적화 ##

단일 노드에 담기 어려운 대규모 모델을 여러 노드에 걸쳐 서빙할 때, 노드 간 통신 오버헤드를 최소화하고 GPU 활용률을 최대화하는 것이 핵심이다. 모델 크기, 지연시간 요구사항, 처리량 목표에 따라 병렬화 전략과 최적화 기법의 조합이 달라지며, 일반적으로 노드 내부는 TP, 노드 간은 PP를 사용하는 하이브리드 구성을 적용한다.
텐서 병렬리즘(Tensor Parallelism, TP)은 레이어의 가중치 텐서를 행 또는 열 방향으로 분할하여 여러 GPU에 나누는 방식으로, 레이어 내부에서 GPU 간 all-reduce 통신이 발생하기 때문에, NVLink 등 고속 인터커넥트를 갖춘 노드 내부에서 주로 사용된다.
파이프라인 병렬리즘(Pipeline Parallelism, PP)은 모델의 레이어를 순차적으로 여러 노드에 배치하는 방식으로 노드 간 통신량이 TP보다 적어 멀티노드 환경에 적합하지만, 파이프라인 버블로 인한 GPU 유휴 시간이 발생할 수 있으므로 마이크로배칭을 통해 이를 줄이는 것이 핵심이다.

### 서빙 프레임워크(추론 엔진) ###
* vLLM: PagedAttention + 텐서/파이프라인 병렬리즘 지원
* TensorRT-LLM: NVIDIA 최적화, 멀티노드 지원(MPI + NCCL)
  
| 항목 | vLLM | TensorRT-LLM |
|------|------|---------------|
| 접근 방식 | 런타임 기반 (모델을 그대로 로드, 동적 최적화) | 컴파일러 기반 (GPU에 맞춰 미리 엔진 빌드) |
| 핵심 기술 | PagedAttention + TP/PP/EP | 커널 퓨전 + TP/PP/EP |
| 콜드스타트 | ~60초 | ~28분 (첫 컴파일), 이후 ~90초 (엔진 재로드) |
| 하드웨어 | NVIDIA + AMD ROCm + Intel | NVIDIA 전용 (H100/A100/Blackwell) |
| 모델 지원 | 수백 개 아키텍처, 새 모델 빠르게 대응 | 주요 모델 위주, 대응 상대적으로 느림 |
| 분산 런타임 | Ray 기반 | MPI + NCCL 기반 |
| 적합한 경우 | 모델 자주 변경, 실험 단계, 멀티벤더, 빠른 스케일아웃 | 단일 모델 장기 프로덕션, 극한 성능, NVIDIA 전용 환경 |


### TP + PP 하이브리드 구성 시 고려사항 ###
* TP degree 선택: 노드 내 GPU 수(보통 8)를 넘지 않도록 설정. NVLink 대역폭(예: A100 NVSwitch 600GB/s)을 넘어 노드 간 TP를 걸면 all-reduce 지연이 급격히 증가.
   * all-reduce = reduce-scatter + all-gather 
* PP stage 분할: 레이어를 균등 분할하는 것이 기본이지만, 임베딩 레이어나 LM head가 있는 첫/마지막 스테이지는 연산량이 다르므로 불균형이 발생한다. vLLM이나 TensorRT-LLM에서는 이를 밸런싱하는 옵션이 있다.  
  #### [vLLM PP Layer Partition](https://discuss.vllm.ai/t/is-it-possible-to-configure-the-order-of-the-pipeline-in-multi-node-deployments/1744) ####
  ```
  # 32개 레이어를 3개 PP 스테이지에 불균등 분배
  VLLM_PP_LAYER_PARTITION=30,30,20 vllm serve meta-llama/Llama-70B \
    --pipeline-parallel-size 3 \
    --tensor-parallel-size 8
  ```
  LM head는 softmax 직전 출력 레이어로 vocab 사이즈(예: 128,000)만큼의 출력 차원을 가진 Linear 레이어로 메모리 사용량이 크므로, 이 예제에서는 GPU 메모리 밸런싱을 위해 마지막 스테이지의 레이어 수를 20개로 줄여 할당하였다.
   
  #### [tensorrt auto_parallel](https://nvidia.github.io/TensorRT-LLM/examples/llm_auto_parallel.html) ####
  ```
  from tensorrt_llm._tensorrt_engine import LLM
  
  llm = LLM(
      model="meta-llama/Llama-70B",
      auto_parallel=True,           # ← 이거
      auto_parallel_world_size=16   # 총 GPU 수
  )
  ```
* 마이크로배치 수: PP 버블을 줄이려면 마이크로배치 수를 PP 스테이지 수의 4배 이상으로 잡는 것이 경험적으로 효과적이다. 다만 인퍼런스에서는 배치 크기가 제한적이라 트레이닝만큼 효과를 보기 어려울 수 있다. (https://tutorialq.com/ai/dl-infrastructure/pipeline-parallelism)
  * Prefill 단계: 입력 시퀀스 전체를 한 번에 처리하므로 마이크로배칭이 가능하고, 트레이닝과 유사하게 버블을 줄일 수 있다.
  * Decode 단계: 토큰 하나씩 순차 생성하므로 마이크로배칭 효과가 제한적이다. 이 단계에서 PP는 본질적으로 스테이지 수만큼의 지연시간 패널티가 발생한다.
Prefill 노드 그룹은 PP로 처리량을 높이고, Decode 노드 그룹은 TP 위주로 지연시간을 최소화하는 식으로 분리할 수 있다.

### Expert Parallelism 심화 ###
MoE 모델에서 EP를 적용할 때의 핵심 트레이드오프:

* All-to-All 통신: 각 토큰이 라우팅된 expert가 있는 노드로 이동해야 하므로 all-to-all 통신이 발생한다. expert 수가 많을수록(DeepSeek-V3는 256개) 통신 패턴이 복잡해진다.
* Expert 로드 밸런싱: 특정 expert에 토큰이 몰리면 해당 노드가 병목이 된다. 트레이닝 시 auxiliary loss로 밸런싱을 유도하지만, 인퍼런스에서는 입력 분포에 따라 불균형이 발생할 수 있다.
* EP + TP + PP 3중 병렬화: 초대형 MoE 모델에서는 세 가지를 모두 조합해야 한다. 예를 들어 TP=4로 노드 내 GPU를 묶고(8 GPU 노드에서 2개의 TP 그룹), expert를 노드 간 EP로 분산하며, 필요시 PP를 추가로 적용하는 식이다.


## 배포시 고려사항 ##
### Health check와 failover ###  
멀티노드 서빙에서 한 노드가 죽으면 전체 파이프라인이 멈추게 된다. Kubernetes 환경에서 pod 단위 재시작보다는 전체 replica 단위 관리가 필요하다. Kubernetes 기본 기능만으로는 이런 "그룹 단위 lifecycle 관리"가 안 되기 때문에, [LeaderWorkerSet](https://lws.sigs.k8s.io/docs/overview/) 같은 커스텀 리소스나 별도의 오케스트레이션 로직이 필요하다.
![](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/images/multi-node-inf-3.png)

### 웜업 ###  
첫 요청 시 CUDA 커널 컴파일, NCCL 초기화 등으로 지연이 크게 발생한다. 배포 후 더미 요청으로 웜업하는 것이 필수이다.   

### 네트워크 토폴로지 인식 ###  
클라우드 환경에서 노드 간 대역폭이 균일하지 않을 수 있기 때문에 placement group(AWS)이나 compact placement policy(GCP)로 노드를 물리적으로 가까이 배치해야 한다.


## [LWS](https://lws.sigs.k8s.io/docs/overview/) ##
LeaderWorkerSet는 Kubernetes SIG에서 관리하는 커스텀 리소스로, pod 그룹을 하나의 복제 단위로 관리하기 위해 만들어 졌다.

### 구조 ###
```
LeaderWorkerSet (replicas: 2, size: 3)
├── Worker Group 0 (= Replica 0)
│   ├── Leader Pod (pod-0)      ← 요청 진입점, 워커 조율
│   ├── Worker Pod (pod-0-1)
│   └── Worker Pod (pod-0-2)
└── Worker Group 1 (= Replica 1)
    ├── Leader Pod (pod-1)
    ├── Worker Pod (pod-1-1)
    └── Worker Pod (pod-1-2)
```
* replicas: Worker Group의 수 (수평 스케일링 단위)
* size: 한 그룹 내 pod 수 (leader + workers)

### 핵심 기능들 ###
* All-or-nothing restart
* 그룹 단위 롤링 업데이트
* 토폴로지 인식 배치 - 같은 그룹의 pod들을 같은 노드/서브넷/존에 배치해서 GPU 간 통신 지연을 최소화.
* 듀얼 템플릿 - Leader pod과 Worker pod에 서로 다른 스펙을 지정 가능.
* HPA 연동

### 실제 vLLM 배포 예시 ###
```
apiVersion: leaderworkerset.x-k8s.io/v1
kind: LeaderWorkerSet
metadata:
  name: vllm-llama70b
spec:
  replicas: 2                    # 2개의 독립적인 서빙 그룹
  leaderWorkerTemplate:
    size: 3                      # 그룹당 3개 pod (leader 1 + worker 2)
    restartPolicy: RecreateGroupOnPodRestart  # ← all-or-nothing
    leaderTemplate:
      spec:
        containers:
        - name: vllm-leader
          image: vllm/vllm-openai:latest
          args:
          - --tensor-parallel-size=8
          - --pipeline-parallel-size=3
          - --model=meta-llama/Llama-3.1-70B-Instruct
          resources:
            limits:
              nvidia.com/gpu: 8
    workerTemplate:
      spec:
        containers:
        - name: vllm-worker
          image: vllm/vllm-openai:latest
          resources:
            limits:
              nvidia.com/gpu: 8
```

## Disaggregated Prefill/Decode ##
```
Prefill (프롬프트 처리)
├── 입력 토큰 수천~수만 개를 한 번에 처리
├── GPU 연산량이 매우 큼 (compute-bound)
├── 배치 처리에 유리 (행렬 곱이 크니까 GPU 활용률 높음)
└── 지연 시간: 수백ms ~ 수초

Decode (토큰 생성)
├── 한 번에 토큰 1개씩 생성
├── 매 스텝마다 KV cache를 읽어야 함 (memory-bound)
├── GPU 연산 자체는 적은데 메모리 대역폭을 많이 씀
└── 지연 시간: 토큰당 수십ms (실시간 스트리밍)
```
```
시간축 →
GPU: [Prefill 요청A ██████████][Decode B ░][Decode C ░][Prefill 요청D ██████████][Decode B ░]...

Decode B, C 입장: Prefill이 GPU를 점유하는 동안 밀려서 ITL(Inter-Token Latency)이 튐
Prefill D 입장: Decode가 끼어들어서 처리량이 떨어짐
```
### Prefill 그룹 ###
* compute-bound이니까 GPU 연산 처리량을 극대화
* 큰 배치를 모아서 한 번에 처리 (throughput 최적화)
* TP=8 등 높은 병렬도로 빠르게 처리
* Decode의 간섭 없이 GPU를 100% 연산에 활용

### Decode 그룹 ###
* memory-bound이니까 메모리 대역폭 활용을 극대화
* 토큰 생성 지연(TPOT)을 일정하게 유지하는 게 중요
* Prefill의 큰 연산이 끼어들지 않으니 지연이 안정적
* 상대적으로 낮은 TP로도 충분할 수 있음 (연산량 자체는 적으니까)

### 트레이드오프 ###
Disaggregated 구성은 ITL을 크게 개선하지만(최대 14배), KV cache 전송 오버헤드로 인해 TTFT가 증가하고, 고정 클러스터에서는 역할 분리로 인한 자원 감소로 처리량이 떨어질 수 있다.
[벤치마크](https://pythonsheets.com/notes/appendix/disaggregated-prefill-decode.html)에서는 단순히 독립 노드를 로드밸런싱한 구성이 처리량과 TTFT 모두에서 Disaggregated를 앞서는 경우도 있었다.
따라서 ITL이 가장 중요한 SLA가 아니라면, 단순한 DP + 로드밸런싱이 더 나은 선택일 수 있다.


