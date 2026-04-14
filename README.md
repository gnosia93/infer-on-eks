# EKS Agentic AI  

본 워크샵은 EKS(Amazon Elastic Kubernetes Service) 환경에서 고성능 GPU 리소스를 효율적으로 관리하며, 단순한 RAG를 넘어 스스로 판단하고 실행하는 Agentic AI를 프로덕션 수준으로 구현하는 것을 목표로 합니다. 오픈 소스 LLM 모델 선정 및 파인튜닝과 더불어, 기업용 서비스의 필수 요건인 보안 가드레일(Guardrails), 정량적 평가(Evaluation), 그리고 지속적 통합/배포(CI/CD) 파이프라인을 포함하고 있으며, 인프라 구축부터 서비스 안정화 및 모니터링까지 LLM 서비스의 전체 생애주기(End-to-End) 에 대한 정보를 제공합니다.


* [L1. EKS 설치하기](https://github.com/gnosia93/eks-agentic-ai/tree/main/iac/tf)

* [L2. PC 노트북 설정](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/2-pc-notebook.md)

* [L3. LLM 평가하기](https://github.com/gnosia93/agentic-ai-eks/blob/main/lesson/3-llm-eval.md)

* [L4. 파인튜닝하기](https://github.com/gnosia93/agentic-ai-eks/blob/main/lesson/4-finetune.md)

* [L5. RAG 파이프라인 설계](https://github.com/gnosia93/agentic-ai-eks/blob/main/lesson/5-rag.md)

* L6. Agentic AI
   - [LangGraph로 RAG 구현](https://github.com/gnosia93/agentic-ai-eks/blob/main/lesson/6-langgraph-rag.md)
   - [@tool 콜링](https://github.com/gnosia93/agentic-ai-eks/blob/main/lesson/6-tool-calling.md)
   - [LangFuse 사용하기](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/6-langfuse.md)
   - [멀티 에이전트 오케스트레이션](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/6-multi-agent.md)
   - [프로덕션 최적화 및 고려사항](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/6-production-optim.md)
   - 사용자 피드백 루프: 응답에 대한 thumbs up/down 수집하고 개선에 반영하는 구조.
   - 프롬프트 엔지니어링 심화: 시스템 프롬프트 설계, few-shot, chain-of-thought 같은 기법

* [L7. 에이전트 가드레일 및 보안 강화](https://github.com/gnosia93/agentic-ai-eks/blob/main/lesson/7.guard-rail.md)
   - NeMo Guardrails를 이용한 입력값 필터링
   - [에이전트 도구 호출 보안: SSRF 방지를 위한 네트워크 격리 (Egress 관리)](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/7-security-ssrf.md)
   - 실전 대응: Prompt Injection 탐지 모델 적용 (Llama Guard 3)
   - 권한 제어: LangGraph를 이용한 Human-in-the-loop(승인 절차) 구현

* [L8. RAG 평가 파이프라인 구성하기](https://github.com/gnosia93/agentic-ai-eks/blob/main/lesson/8.eval-framework.md)

* L9. CI/CD 파이프라인
   - 프롬프트 버전 관리
   - 에이전트 로직 테스트 자동화
   - 배포 파이프라인

* L10. EKS 배포하기
   - [vLLM 인퍼런스](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/10-vllm-inference.md)  
   - [TensorRT-LLM 인퍼런스](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/10-tensorrt-inference.md)
   - [KEDA 기반 오토 스케일링](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/10-keda-autoscaling.md)

* [L11. 멀티노드 인퍼런스 구성 및 최적화](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/11-multi-node-inference.md)

* [L12. Post Training](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/12-post-training.md)

### _Appendix_ ###

* [TensorRT-LLM 연산최적화](https://github.com/gnosia93/infer-on-eks/blob/main/lesson/a1-tensorrt-llm.md)
* [Prometheus/Loki Stack](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/a2-prometheus-loki.md)   
* [LOKI에 K8S 이벤트 저장하기](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/a3-k8s-event.md)
* [K8S 컨트롤 플레인](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/a4-k8s-controlplan.md)
* [Harness Engineering](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/a5.harness-eng.md)
* [promptfoo 로 모델 평가하기](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/a7.promptfoo.md)
* [인퍼런스용 GPU 선정하기](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/a8-model-fit-gpu.md)

     
## 레퍼런스 ##
* https://github.com/NVIDIA/Model-Optimizer/tree/main 









