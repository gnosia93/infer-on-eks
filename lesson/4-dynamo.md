![](https://github.com/gnosia93/post-training/blob/main/lesson/images/nvidia-dynamo-1.png)

### NVIDIA Dynamo (차세대 분산 추론 프레임워크) ###
Triton Inference Server의 후속 기술로, 대규모 분산 환경에서 생성형 AI 및 추론 모델을 효율적으로 배포하는 하이레벨 프레임워크.

* 대규모 분산 환경: 수천 개의 GPU에서 LLM을 구동할 때 필요한 오케스트레이션(요청 라우팅, GPU 스케줄링)을 처리.
* Disaggregated Serving: 프리필(prefill, 프롬프트 분석)과 디코드(decode, 토큰 생성) 단계를 분리하여 GPU 자원을 최적화.
* 엔진 Agnostic: TensorRT-LLM, vLLM, SGLang 등 다양한 고속 추론 엔진을 백엔드로 유연하게 선택 가능.



### TensorRT 시리즈 (모델 최적화 및 런타임) ###
* 정의: NVIDIA GPU에서 딥러닝 모델의 추론 속도를 극대화하는 저레벨(Low-level) 최적화 SDK 및 런타임.
* 주요 특징:
  * 모델 엔진 생성: PyTorch, ONNX 등의 모델을 TensorRT 엔진 파일(.engine)로 변환.
  * 핵심 기술: 레이어 융합(Layer Fusion), 커널 오토튜닝, 양자화(INT8, FP8) 등을 통해 고속 추론.
  * TensorRT-LLM: LLM에 특화된 TensorRT 버전으로, In-flight batching 등 최적화 기술 제공.
  * 사용 목적: 단일 또는 다중 GPU 환경에서 개별 모델의 지연 시간(Latency) 최소화 및 처리량 극대화. 

### 주요 차이점 요약 ###
|구분| 	NVIDIA Dynamo|	TensorRT / TRT-LLM|
|---|---|---|
|주 역할|	분산 추론 서버/오케스트레이터|	모델 최적화 런타임 엔진|
|작동 레이어|	하이레벨 (Infrastructure, Serving)|	저레벨 (Graph, Kernels, Hardware)|
|주요 대상|	대규모 클러스터 (Multi-node/GPU)| 단일/멀티 GPU 인스턴스|
|핵심 기술|	분산 스케줄링, Disaggregated Serving|	양자화(FP8/INT8), Layer Fusion|
|관계|	요청 관리자 (Backend로 TRT 사용)|	실제 연산 최적화기|


* LLM(추론)에서의 Prefill
Prefill는 사용자 입력(프롬프트)을 한 번에 처리해 문맥 정보를 계산하고 KV 캐시를 생성하는 단계,
이후 Decode 단계는 다음 토큰을 1개씩 순차적으로 생성하는 과정



## 레퍼런스 ##
* https://github.com/ai-dynamo/dynamo
* [NVIDIA Dynamo: 차세대 분산 추론 프레임워크 리뷰](https://www.sktenterprise.com/bizInsight/blogDetail/dev/14476)
