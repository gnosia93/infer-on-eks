[워크샵] Amazon EKS 기반 오픈 웨이트 LLM 인퍼런스 시스템 구축

```
1. 워크샵 개요 및 환경 준비 (Module 1)
⚬	LLM 인퍼런스 및 EKS 아키텍처 이해
⚬	오픈 웨이트 LLM(Llama 3, Mistral, Qwen 등) 아키텍처 개요
⚬	EKS 기반 서빙의 장점: 탄력성, 멀티 텐런시, 복윈력(Resilience)
⚬	실습 환경 프로비저닝 (eksctl / Terraform)
⚬	EKS 클러스터 생성 및 Control Plane 설정
⚬	필수 Add-on 설치 (AWS Load Balancer Controller, EBS CSI Driver 등)
⚬	Hugging Face API 토큰 및 클러스터 Secret 설정

2. GPU 인프라 자동화 및 최적화 (Module 2)
⚬	Karpenter를 활용한 GPU 노드 자동 스케일링
⚬	Karpenter 개념 및 EKS 연동
⚬	NodePool 및 EC2NodeClass 정의 (NVIDIA g5/p4d/p5 인스턴스 타깃팅)
⚬	NVIDIA GPU Operator 설정
⚬	GPU Driver, CUDA, Container Toolkit 자동 배포
⚬	Multi-Instance GPU (MIG) 및 GPU Sharing/Time-Slicing 실습

3. 고성능 LLM 서빙 프레임워크 배포 (Module 3)
⚬	서빙 엔진 선정 및 특징 비교
⚬	vLLM / TGI (Text Generation Inference) / TensorRT-LLM 특징 비교
⚬	vLLM 기반 LLM 서빙 배포 실습
⚬	Hugging Face 모델 로딩 및 PV/PVC(EFS/S3 Mount) 캐싱 전략
⚬	PagedAttention 및 Continuous Batching 옵션 최적화
⚬	Kubernetes Deployment 및 Service(ClusterIP/LoadBalancer) 작성
⚬	Tensor Parallelism(모델 병렬화) 설정
⚬	멀티 GPU(예: tp=2 또는 tp=4) 환경에서의 Pod 배치 및 리소스 Limit 설정

4. 트래픽 제어 및 자동 스케일링 (Module 4)
⚬	Ingress 및 API Gateway 설정
⚬	AWS ALB (Application Load Balancer) 연동 및 TLS 설정
⚬	OpenAI 호환 API 엔드포인트 테스트 (cURL, Python Client)
⚬	KEDA 기반 고급 오토스케일링 (HPA)
⚬	Prometheus 메트릭 연동 (vLLM의 vllm:num_requests_waiting 메트릭 활용)
⚬	대기 큐(Queue) 기반 GPU 노드/Pod Horizontal Pod Autoscaler(HPA) 구성

5. 관찰 가능성(Observability) 및 운영 최적화 (Module 5)
⚬	LLM 메트릭 수집 및 모니터링
⚬	Prometheus + Grafana 대시보드 구축
⚬	핵심 지표 모니터링: TTFT (Time to First Token), TPOT (Time per Output Token), GPU Utilization, KV Cache Usage
⚬	비용 절감 및 운영 팁
⚬	Spot 인스턴스 활용 전략 및 데이터 프리페칭(Pre-fetching)
⚬	S3 / AWS DataSync를 활용한 모델 가중치 빠른 로딩 기법

6. 핸즈온 랩 (Hands-on Lab): 엔드투엔드 파이프라인 구축 (Module 6)
⚬	시나리오 실습
⚬	Karpenter 노드 0에서 시작 ‭$\rightarrow$‬ API 요청 수신 ‭$\rightarrow$‬ GPU 노드 동적 생성 ‭$\rightarrow$‬ vLLM Pod 스케일 아웃 ‭$\rightarrow$‬ 인퍼런스 응답 ‭$\rightarrow$‬ Scale In 테스트
⚬	Wrap-up & Q&A
⚬	실습 리소스 정리 (eksctl delete, Karpenter cleanup)
💡 워크샵 운영 팁
⚬	예상 소요 시간: 반일(4시간) 코스 또는 전일(6~7시간) 코스로 구성하기 적합합니다.
⚬	실습 비용 제어: GPU 인스턴스(g5.xlarge, g5.12xlarge 등)는 비용이 높으므로, 실습 직후 Karpenter 스케일인 정책을 타이트하게 잡거나 마지막에 리소스 삭제 단계를 반드시 포함시키는 것이 좋습니다.
```
