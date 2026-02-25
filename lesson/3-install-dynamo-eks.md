## NVIDIA Dyanmo (차세대 분산 추론 프레임워크) ##
NVIDIA Dynamo는 Triton Inference Server의 후속 기술로 대규모 데이터 센터 환경에서 생성형 AI 모델의 추론 성능을 극대화하기 위해 설계된 오픈 소스 분산 추론 프레임워크로 Prefill(입력 처리)과 Decode(출력 생성) 단계를 서로 다른 GPU 노드로 분리하여 병렬로 처리하는 분리형 서빙(Disaggregated Serving) 아키텍처를 핵심으로 한다. 이 과정에서 NIXL을 활용해 노드 간 KV 캐시 데이터를 연산 중단 없이 초고속으로 전송함으로써 전반적인 추론 지연 시간을 획기적으로 단축시키고, 사용자의 요청이 들어올 때 기존 캐시 데이터가 위치한 최적의 노드를 실시간으로 찾아주는 지능형 라우팅 기능을 수행하며, CPU DRAM이나 SSD까지 활용하는 계층형 메모리 관리를 통해 대규모 동시 접속 상황에서도 안정적인 서비스 성능을 유지한다. TensorRT-LLM, vLLM, SGLang 기존 엔진들과 유연하게 결합하여 거대 언어 모델(LLM) 서빙 능력을 극대화하는 통합 프레임워크 이다.
![](https://github.com/gnosia93/interence-on-eks/blob/main/lesson/images/nvidia-dynamo-1.png)


### NIXL(NVIDIA Inference Transfer Library)의 작동 원리 ###
* 연산 자원의 분리: NIXL은 통신을 위해 GPU의 연산 유닛(SM)을 사용하는 기존 NCCL 방식과 달리, GPU 내부의 전용 복사 엔진(Copy Engine)을 직접 제어하여 추론 연산과 데이터 전송을 완벽하게 병렬화.
* 커널 오버헤드 제거: 데이터를 보낼 때마다 GPU 커널을 매번 실행(Launch)하지 않고, CPU가 하드웨어를 직접 조작하는 비동기 방식을 채택하여 짧은 메시지를 빈번하게 주고받는 추론 환경에서 지연 시간을 획기적으로 줄임.
* 직통 데이터 경로(P2P & RDMA): 서버 내부에서는 NVLink를 통한 GPU 간 직접 접근(P2P)을, 서버 간에는 GPUDirect RDMA를 활용하여 CPU 메모리 거침 없이 GPU HBM 간의 고속도로를 생성.
* 하드웨어 레벨의 메모리 관리: 전송할 메모리 영역을 물리적으로 고정하는 Pinning과 물리 주소를 하드웨어에 직접 전달하는 Memory Registration을 통해, OS나 GPU SM의 간섭 없이도 안전하고 정확한 데이터 이동을 보장.
* 추론 효율의 극대화: 결과적으로 데이터 전송 중에도 GPU가 연산에만 100% 집중할 수 있게 하여, 특히 LLM의 KV Cache 전송이나 분산 추론 시 기존 대비 약 30~50% 이상의 성능 향상.


### NVIDIA Dynamo Vs TensorRT ###
|구분| 	NVIDIA Dynamo|	TensorRT / TRT-LLM|
|---|---|---|
|주 역할|	분산 추론 서버/오케스트레이터|	모델 최적화 런타임 엔진|
|작동 레이어|	하이레벨 (Infrastructure, Serving)|	저레벨 (Graph, Kernels, Hardware)|
|주요 대상|	대규모 클러스터 (Multi-node/GPU)| 단일/멀티 GPU 인스턴스|
|핵심 기술|	분산 스케줄링, Disaggregated Serving|	양자화(FP8/INT8), Layer Fusion|
|관계|	요청 관리자 (Backend로 TRT 사용)|	실제 연산 최적화기|



## 레퍼런스 ##

* [Microservices Communication with NATS](https://www.geeksforgeeks.org/advance-java/microservices-communication-with-nats/)
