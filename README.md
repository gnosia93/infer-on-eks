# EKS Agentic AI  

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
    - GPU 노드에 vLLM 배포
    - HPA (Horizontal Pod Autoscaler) 설정
    - Ingress + 로드밸런싱

* [9. Post Training](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/9.post-training.md)




### _Appendix_ ###

* [1. EKS 생성하기](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/1-create-eks.md)

* [2. GPU 노드풀 생성](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/2-gpu-nodepool.md)

* [3. TensorRT-LLM](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/3-tensorrt-llm.md)
   
* [4. NVIDIA Dyanmo](https://github.com/gnosia93/post-training/blob/main/lesson/4-dynamo.md)
  - [로컬 Docker 배포하기](https://github.com/gnosia93/interence-on-eks/blob/main/lesson/4-dynamo-docker.md) 
  - [EKS 배포하기](https://github.com/gnosia93/interence-on-eks/blob/main/lesson/4-dynamo-eks.md) 

### todo ###
* 각각의 모듈에 대해서 도커를 만들어서 ecr 에 푸시한다.
* gitlab 과 연동하여 코드 repo 를 만들고 ci/cd 
* appendix 내용을 어떻게 워크샵에 잘 녹여낼지 고민이 필요
* agentic ai 에 대한 어플리케이션 개발 부터 open source 기반의 LLM serving infra 까지 어떻게 잘 녹여낼지 고민이 필요하다..
* 다루는 내용이 너무 많은 관계로, 어떻게 하면 깔끔하게 핵심만 다룰 수 있을지????      
   * eks 클러스터 생성 및 gpu 노드풀과 같은 인프라적인 부분은 terraform 으로 사전 빌드.
   * dynamo inference 엔진의 경우 상당히 복잡하므로 어떻게 워크샵에 녹여내야 할지 ??? prefill-decode 구조는 생략? 아니면 dynamo 는 다루지 말고 vLLM 만 도커라이징 ??? 
     
## 레퍼런스 ##

* https://github.com/NVIDIA/Model-Optimizer/tree/main 
* https://github.com/huggingface/accelerate









