# EKS Agentic AI  

* [L0. EKS 설치](https://github.com/gnosia93/eks-agentic-ai/tree/main/iac/tf)

* [L1. 노트북 환경 설정](https://github.com/gnosia93/agentic-ai-eks/blob/main/lesson/1.start.md)

* [L2. LLM 평가하기](https://github.com/gnosia93/agentic-ai-eks/blob/main/lesson/2-llm-eval.md)

* [L3. 파인튜닝하기](https://github.com/gnosia93/agentic-ai-eks/blob/main/lesson/3-finetune.md)

* [L4. RAG 파이프라인 설계](https://github.com/gnosia93/agentic-ai-eks/blob/main/lesson/4-rag.md)

* L5. Agentic AI
   - [LangGraph로 RAG 구현](https://github.com/gnosia93/agentic-ai-eks/blob/main/lesson/5-langgraph-rag.md)
   - [@tool 콜링](https://github.com/gnosia93/agentic-ai-eks/blob/main/lesson/5-tool-calling.md)
   - [LangFuse 사용하기](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/5-langfuse.md)

* [6. 가드레일 구성하기](https://github.com/gnosia93/agentic-ai-eks/blob/main/lesson/6.guard-rail.md)

* [7. RAG 평가 파이프라인 구성하기](https://github.com/gnosia93/agentic-ai-eks/blob/main/lesson/7.eval-framework.md)

* [8. EKS 배포하기]
    - Helm Chart 구성
    - GPU 노드에 vLLM / TensorRT-LLM 배포
    - HPA (Horizontal Pod Autoscaler) 설정
    - Ingress + 로드밸런싱

* [9. Post Training](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/9.post-training.md)


### _Appendix_ ###

* [TensorRT-LLM 연산최적화](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/a1-tensorrt-llm.md)
* [Prometheus/Loki Stack](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/a2-prometheus-loki.md)   
* [LOKI에 K8S 이벤트 저장하기](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/a3-k8s-event.md)
* [K8S 컨트롤 플레인](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/a4-k8s-controlplan.md)
* [Harness Engineering]()
    
### todo ###
* 각각의 모듈에 대해서 도커를 만들어서 ecr 에 푸시한다.
* gitlab 과 연동하여 코드 repo 를 만들고 ci/cd 
* appendix 내용을 어떻게 워크샵에 잘 녹여낼지 고민이 필요
* agentic ai 에 대한 어플리케이션 개발 부터 open source 기반의 LLM serving infra 까지 어떻게 잘 녹여내야 한다.
* vLLM, TensorRT-LLM, SGLang 등 추론 서빙 엔진 / 추론 최적화 
* KV Cache 최적화, Prefill/Decode 분리, Continuous Batching, Speculative Decoding
* 에이전트 오케스트레이션, 하네스 엔지니어링
* 장시간 실행되는 에이전트의 상태 관리, 복구, 모니터링
* LangGraph / LangGraph.
  
     
## 레퍼런스 ##

* https://github.com/NVIDIA/Model-Optimizer/tree/main 
* https://github.com/huggingface/accelerate









