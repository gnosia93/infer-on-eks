# ☸️ 쿠버네티스 기반 오픈 웨이트 LLM 추론 아키텍처 핵심 설계 가이드

쿠버네티스(K8s) 환경에서 오픈 웨이트(Open-weight) LLM 추론 아키텍처를 설계할 때는 일반 웹 서비스와 달리 **막대한 GPU 메모리 점유, 긴 응답 지연 시간(Latency), 그리고 트래픽 급증 시의 스케일링 병목**을 해결하는 것이 핵심입니다.

보험 약관 RAG 시스템처럼 정확도와 빠른 응답(TTFT)이 중요한 프로덕션 환경을 기준으로 **6가지 핵심 설계 고려사항**을 정리합니다.

---

## 1. 고성능 추론 엔진(Inference Engine) 선택
Hugging Face `transformers`의 기본 `generate()` 방식은 동시 접속 처리(Batching)가 약해 운영 환경에 적합하지 않습니다.

* **vLLM (가장 권장):** PagedAttention과 Continuous Batching을 지원해 동시 요청 처리량(Throughput)이 압도적이며, OpenAI 호환 API 서버를 즉시 띄울 수 있습니다. 학습된 **LoRA 어댑터를 동적으로 여러 개 갈아끼우는(Multi-LoRA)** 기능도 뛰어납니다.
* **TensorRT-LLM / NVIDIA Triton:** NVIDIA GPU 성능을 극한으로 끌어내야 하는 대규모 환경에 적합하지만, 모델 컴파일 및 운영 복잡도가 높습니다.
* **SGLang:** 구조화된 출력(JSON 강제 등)과 복잡한 프롬프트 캐싱(RadixAttention)이 많은 RAG 파이프라인에서 매우 빠른 속도를 냅니다.

---

## 2. GPU 리소스 할당 및 분할 전략
GPU는 고비용 자원이므로 모델 크기(예: 7B~32B)와 양자화(AWQ, FP8 등) 여부에 따라 효율적으로 분할하거나 병렬화해야 합니다.

* **단일 노드 멀티 GPU (Tensor Parallelism):** 32B 이상 대형 모델이 GPU 1장 VRAM에 들어가지 않을 경우, 한 파드(Pod)에 여러 GPU를 할당(`tensor-parallel-size`)하고 GPU 간 고속 통신(NVLink)을 활용합니다.
* **GPU 분할 (MIG / Time-Slicing):** 7B~8B 경량 모델이나 임베딩/리랭커 모델을 여러 개 띄울 때는 NVIDIA MIG(Multi-Instance GPU)로 물리적 파티셔닝을 하거나 Time-Slicing으로 GPU 1장을 여러 파드가 공유하도록 설계합니다.

---

## 3. 모델 가중치(Weights) 로딩 및 스토리지 최적화
수십 GB에 달하는 모델 파일을 컨테이너 이미지에 포함하면 이미지 크기가 비대해져 배포(Pull)에 수십 분이 소요됩니다.

* **스토리지 분리:** 컨테이너 이미지에는 추론 엔진(vLLM 등)만 담고, 모델 파일은 **고성능 공유 스토리지(NVMe 기반 PVC, Lustre, S3/MinIO)**에 미리 저장한 뒤 파드 시작 시 마운트합니다.
* **초기화 속도 개선:** Run:ai Model Streamer나 고속 로컬 캐시(HostPath / DaemonSet 프리로딩)를 활용해 스케일 아웃 시 모델이 GPU VRAM으로 올라가는 콜드 스타트(Cold Start) 시간을 최소화해야 합니다.

---

## 4. LLM 특화 오토스케일링 (KEDA & GPU 메트릭)
일반적인 CPU/메모리 기반 HPA(Horizontal Pod Autoscaler)는 LLM 워크로드에서 제대로 작동하지 않습니다. (GPU는 항상 90% 이상 점유되어 있거나 유휴 상태이기 때문)

* **큐/KV 캐시 기반 스케일링:** **KEDA**와 Prometheus를 연동하여 vLLM이 노출하는 핵심 메트릭을 기준으로 파드 수를 조절합니다.
  * `vllm:num_requests_waiting` (대기 중인 요청 수)
  * `vllm:gpu_cache_usage_perc` (KV 캐시 메모리 사용률)
* **노드 오토스케일러:** GPU 노드가 부족할 때 클라우드/온프레미스 GPU 노드를 빠르게 확장하기 위해 **Karpenter** 또는 Cluster Autoscaler를 조합합니다.

---

## 5. 네트워크 및 AI 게이트웨이(LLM Gateway) 라우팅
LLM 추론은 일반 REST API와 달리 **스트리밍(SSE)** 통신이 기본이며, 요청당 처리 시간이 깁니다.

* **인그레스 타임아웃 조정:** NGINX Ingress나 Envoy 설정에서 `proxy-read-timeout` 등을 넉넉히(예: 120초~300초) 늘리고, 스트리밍 응답이 중간에 버퍼링되지 않도록 `proxy-buffering off` 설정이 필수입니다.
* **KV 캐시 친화적 라우팅 (Prefix-Aware Routing):** RAG 시스템에서는 시스템 프롬프트나 동일한 약관 청크가 반복해서 들어옵니다. 일반 라운드로빈(Round-Robin) 대신, **이미 해당 프롬프트의 KV 캐시를 보유한 파드로 요청을 보내는 스마트 라우터**(Kubernetes Gateway API Inference Extension, LiteLLM, vLLM Router 등)를 앞단에 두면 첫 토큰 응답 속도(TTFT)가 획기적으로 빨라집니다.

---

## 6. 관측 가능성(Observability) 및 Multi-LoRA 서빙
운영 중 품질 저하나 병목을 파악하기 위해 일반 시스템 모니터링 외에 LLM 전용 지표를 수집해야 합니다.

* **핵심 추적 지표:**
  * **TTFT (Time To First Token):** 사용자가 질문 후 첫 글자가 찍힐 때까지 걸리는 시간 (체감 속도)
  * **TPOT (Time Per Output Token) / ITL:** 토큰당 생성 속도
  * **DCGM Exporter:** GPU 온도, 전력, VRAM 사용량, SM 점유율 모니터링
* **Multi-LoRA 동적 스위칭:** **고객용 어댑터**와 **직원용 어댑터**가 나뉘어 있다면, 베이스 모델 파드 1세트만 띄운 상태에서 요청 모델명(`model="insurance-customer"`, `model="insurance-agent"`)에 따라 vLLM이 내부에서 LoRA 가중치만 즉시 스위칭하도록 구성해 GPU 인프라 비용을 절감합니다.

---

## 💡 아키텍처 추천 구성 요약 (보험 약관 RAG 프로덕션 기준)

| 계층 (Layer) | 추천 기술 스택 | 핵심 역할 |
| :--- | :--- | :--- |
| **추론 엔진** | **vLLM** (AWQ/FP8 + Multi-LoRA) | PagedAttention 기반 고속 배치 처리 및 고객/직원 어댑터 동적 전환 |
| **AI 게이트웨이** | **Envoy AI Gateway / LiteLLM** | SSE 스트리밍, Rate Limiting, Prefix-Aware 라우팅, Fallback 처리 |
| **오토스케일링** | **KEDA + Karpenter** | 대기 큐(`num_requests_waiting`) 기반 파드 확장 및 GPU 노드 프로비저닝 |
| **스토리지** | **NVMe PVC / MinIO (S3)** | 컨테이너 이미지 경량화 및 모델 가중치 고속 마운트 |
| **모니터링** | **Prometheus + Grafana + DCGM** | TTFT, TPOT, KV 캐시 점유율 및 GPU 하드웨어 상태 실시간 관측 |
