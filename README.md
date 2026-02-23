# triton-on-eks

### TensorRT-LLM ###
* 주피터 노트북 설치하기..
* [1. 설치하기](https://github.com/gnosia93/inference-on-eks/blob/main/lesson/1-install.md)
* fastapi 붙여서 웹서버 구현하기 


### Triton 인퍼런스 서버 ###
* https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/introduction/index.html
* https://github.com/triton-inference-server/server
* https://github.com/triton-inference-server/server/blob/main/deploy/aws/README.md


---


TensorRT-LLM '자체'는 추론 엔진(엔진 오일/부품)이고, Triton은 이를 감싸서 서비스하는 '자동차(완성체)'와 같습니다.

1. TensorRT-LLM만 사용할 때 (라이브러리 수준)
TensorRT-LLM은 고성능 연산을 가능하게 하는 핵심 로직을 가지고 있지만, "밖에서 접속 가능한 서버" 형태는 아닙니다.
In-flight Batching: 알고리즘은 들어있지만, 실제로 여러 사용자 요청을 받아서 순서를 짜고 큐(Queue)에 넣는 '스케줄러 매니저' 기능은 직접 코딩해야 합니다.
인터페이스: HTTP나 gRPC 통신 기능이 없습니다. 그래서 앞서 질문하신 것처럼 FastAPI 같은 것을 직접 붙여서 통신 기능을 만들어야 합니다.
멀티 모델 관리: 메모리에 여러 모델을 올리고 자원을 분배하는 로직을 직접 짜야 합니다.

2. Triton + TensorRT-LLM 조합 (서빙 플랫폼)
NVIDIA가 Triton TensorRT-LLM Backend를 만든 이유가 바로 이것입니다.
스케줄링: TRT-LLM의 In-flight Batching 알고리즘을 사용자가 따로 코딩할 필요 없이, 설정 파일(config.pbtxt)만 건드리면 Triton이 알아서 최적으로 스케줄링해줍니다.
인터페이스: 서버를 띄우자마자 NVIDIA Triton의 표준 API (HTTP/gRPC)가 즉시 활성화됩니다.
멀티 모델: 한 GPU에 Llama-3와 Mistral을 동시에 올리고, 들어오는 요청에 따라 자원을 분배하는 관리를 Triton이 전담합니다.

3. 그럼 vLLM은?
vLLM은 특이하게도 [추론 엔진 + 스케줄러 + API 서버]를 하나로 꽉꽉 눌러 담은 형태입니다.
그래서 vLLM은 TensorRT-LLM처럼 "라이브러리"라고 부르기보다 "서빙 엔진"이라고 부릅니다.
사용자 입장에서는 vLLM이 훨씬 편하지만, 성능의 한계까지 쥐어짜거나 비전/음성 모델 등과 통합할 때는 Triton + TRT-LLM 조합이 더 강력합니다.


## 레퍼런스 ##
* https://www.index.dev/skill-vs-skill/ai-vllm-vs-tgi-vs-tensorrt-llm 
* https://github.com/NVIDIA/TensorRT-LLM
* https://catalog.workshops.aws/genai-on-eks/en-US
* [TensforRT vs vLLM](https://ncsoft.github.io/ncresearch/512f982a1564b5441d432935a7098146226e20b7)
