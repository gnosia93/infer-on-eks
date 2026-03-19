# Agentic AI on EKS 

* [1. 노트북 환경 설정](https://github.com/gnosia93/agentic-ai-eks/blob/main/lesson/1.start.md)

* [2. LLM 평가하기](https://github.com/gnosia93/agentic-ai-eks/blob/main/lesson/2-llm-eval.md)

* [3. 파인튜닝하기](https://github.com/gnosia93/agentic-ai-eks/blob/main/lesson/3-finetune.md)

* [4. RAG 설계](https://github.com/gnosia93/agentic-ai-eks/blob/main/lesson/4-rag.md)

* [5. Agentic AI 구현하기]
   - LangGraph로 에이전트 구성
   - Tool Calling (함수 호출)
   - Multi-Agent 패턴 (Planner → Executor → Reviewer)
   - 메모리 관리 (대화 히스토리)
   - LangFuse

* [6. 가드레일 구성하기]
   - Input/Output 필터링
   - NLI 기반 환각 검증
   - 프롬프트 인젝션 방어

* [7. 모니터링 구성하기]
   - Prometheus + Grafana
   - 응답 시간, 토큰 사용량, 검색 품질 메트릭
   - LLM-as-Judge 비동기 평가

* [8. 평가 파이프라인 구성하기](https://github.com/gnosia93/agentic-ai-eks/blob/main/lesson/8.eval-framework.md)
   - RAGAS 프레임워크
   - 도메인 평가 데이터셋 구축
   - CI/CD에 평가 통합

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

    

## 레퍼런스 ##

* https://github.com/NVIDIA/Model-Optimizer/tree/main 
* https://github.com/huggingface/accelerate









