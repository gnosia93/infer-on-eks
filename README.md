# EKS Agentic AI  

* [L1. 노트북 환경 설정](https://github.com/gnosia93/agentic-ai-eks/blob/main/lesson/1.start.md)

* [L2. LLM 평가하기](https://github.com/gnosia93/agentic-ai-eks/blob/main/lesson/2-llm-eval.md)

* [L3. 파인튜닝하기](https://github.com/gnosia93/agentic-ai-eks/blob/main/lesson/3-finetune.md)

* [L4. RAG 파이프라인 설계](https://github.com/gnosia93/agentic-ai-eks/blob/main/lesson/4-rag.md)

* L5. Agentic AI
   - [LangGraph로 RAG 구현](https://github.com/gnosia93/agentic-ai-eks/blob/main/lesson/5-langgraph-rag.md)
   - [@tool 콜링](https://github.com/gnosia93/agentic-ai-eks/blob/main/lesson/5-tool-calling.md)
   - Multi-Agent 패턴 (Planner → Executor → Reviewer)
   - 메모리 관리 (대화 히스토리)
   - [LangFuse](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/5-langfuse.md)

* [6. 가드레일 구성하기](https://github.com/gnosia93/agentic-ai-eks/blob/main/lesson/6.guard-rail.md)

* [7. 모니터링 구성하기]
   - Prometheus + Grafana
   - 응답 시간, 토큰 사용량, 검색 품질 메트릭
   - LLM-as-Judge 비동기 평가

* [8. 평가 파이프라인 구성하기](https://github.com/gnosia93/agentic-ai-eks/blob/main/lesson/8.eval-framework.md)

* [9. 로컬 Docker 배포하기]
    - Docker Compose (FastAPI + vLLM + VectorDB + Monitoring)
    - 통합 테스트

* [10. EKS 배포하기]
    - Helm Chart 구성
    - GPU 노드에 vLLM 배포
    - HPA (Horizontal Pod Autoscaler) 설정
    - Ingress + 로드밸런싱

* [11. Post Training]
   - DPO로 선호도 정렬
   - 평가 → 재학습 루프



### _Appendix_ ###

* [1. EKS 생성하기](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/1-create-eks.md)

* [2. GPU 노드풀 생성](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/2-gpu-nodepool.md)

* [3. TensorRT-LLM](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/3-tensorrt-llm.md)
   
* [4. NVIDIA Dyanmo](https://github.com/gnosia93/post-training/blob/main/lesson/4-dynamo.md)
  - [로컬 Docker 배포하기](https://github.com/gnosia93/interence-on-eks/blob/main/lesson/4-dynamo-docker.md) 
  - [EKS 배포하기](https://github.com/gnosia93/interence-on-eks/blob/main/lesson/4-dynamo-eks.md) 

* https://developer.nvidia.com/blog/optimizing-llms-for-performance-and-accuracy-with-post-training-quantization/
    

## 레퍼런스 ##

* https://github.com/NVIDIA/Model-Optimizer/tree/main 
* https://github.com/huggingface/accelerate









