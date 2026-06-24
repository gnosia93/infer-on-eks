### LeaderWorkerSet (LWS)
•	단일 파드로 띄우기 힘든 대형 LLM을 위해, 1개의 Leader 파드와 N개의 Worker 파드를 하나의 그룹으로 묶어주는 쿠버네티스 네이티브 Custom Resource 정의(CRD)입니다. multi-node 추론 시 네트워크 및 라이프사이클을 효율적으로 제어합니다.
### Ray 인프라 (KubeRay)
•	Ray Cluster: LLM 서빙 프레임워크(vLLM, TGI)를 EKS 위에서 분산 처리하기 위한 백엔드로 Ray를 활용합니다.
•	CPU 인퍼런스 (그라비톤): AWS Graviton(ARM64) 기반 c7g 인스턴스를 활용하여, 임베딩 모델이나 경량 모델 추론 시 가성비를 극대화합니다.
•	GPU 인퍼런스: vLLM + Ray 조합으로 Tensor Parallelism(TP) 및 Pipeline Parallelism(PP)을 구현하여 복수의 GPU 노드에서 분산 추론을 수행합니다.
•	AWS 인퍼런시아: vLLM이 최신 버전에서 AWS Neuron을 지원함에 따라, KubeRay와 Inf2를 연동하여 비용을 절감하는 분산 추론 환경을 구성합니다.
---
[Part 1] LeaderWorkerSet 개념 및 이론 (40분)

*	왜 LWS가 필요할까? (10분)
*	기존 쿠버네티스 ReplicaSet/Deployment의 한계 (대형 LLM을 여러 GPU 노드에 쪼개 올릴 때 그룹 단위 제어가 어려움)
*	대장(Leader)과 일꾼(Worker) 구조의 필요성
*	LWS 핵심 아키텍처 이해 (20분)
*	복제 그룹(Replicas) 단위로 묶이는 Pod 구조
*	네트워크 아키텍처: Leader와 Worker 간의 초고속 상호 통신 및 헬스 체크 방식
*	하나의 일꾼(Worker)이라도 죽으면 그룹 전체를 안전하게 재시작하는 메커니즘
*	vLLM / Hugging Face와의 연계 원리 (10분)
*	텐서 병렬화(Tensor Parallelism) 및 파이프라인 병렬화(Pipeline Parallelism)를 LWS에 매핑하는 방법

---
[Part 2] EKS LWS 환경 구축 실습 (40분)

*	Step 1: LWS 컨트롤러 설치 (15분)
  *	EKS 클러스터에 LeaderWorkerSet 오퍼레이터 배포하기
* **Step 2: GPU 노드 및 스케줄링 설정 (15분)**
  * GPU 자원(NVIDIA 토천 및 드라이버) 확인
  * 가용 영역(AZ) 내에서 Leader와 Worker들이 흩어지지 않고 같은 네트워크 스위치(지연 시간 최소화)에 묶이도록 `TopologySpreadConstraints` 설정하기
* **Step 3: 환경 검증 (10분)**
  * 컨트롤러가 정상 동작하는지 Pod 상태 확인

---

### [Part 3] 오픈소스 LLM(Llama 3) 분산 서빙 실습 (50분)

* **Step 1: LWS 매니페스트(YAML) 작성 및 배포 (20분)**
  * 1개의 Leader와 2개의 Worker를 한 팀으로 묶는 LWS 설정 파일 작성
  * vLLM 엔진을 얹어 모델 파티셔닝 설정 주입하기
* **Step 2: 분산 추론 레이어 작동 확인 (15분)**
  * `kubectl get lws` 명령어로 리더-워커 그룹 상태 모니터링
  * 리더 Pod의 로그를 통해 워커들이 정상적으로 모델 조각을 나누어 로드했는지 확인
* **Step 3: 추론(Inference) 테스트 (15분)**
  * 리더 Pod의 서비스 엔드포인트로 질문(Prompt)을 던져 분산 추론 답변 속도 확인

---

### [Part 4] 장애 복구(Failover) 및 트러블슈팅 실습 (20분)

* **시나리오: 의도적으로 Worker Pod 하나를 강제 삭제(Kill)하기**
  * 하나의 Worker가 죽었을 때 LWS 가 그룹 전체의 정합성을 위해 Leader와 나머지 Worker를 어떻게 우아하게 재시작(Eviction & Restart)하는지 눈으로 확인
  * LLM 서빙 환경에서 불완전한 모델 파편화를 막는 이 메커니즘의 중요성 토론

---

## 🎯 이 워크샵을 마치면 수강생이 얻는 것 ##
1. **분산 서빙의 실무 자신감:** GPU 1대에 안 들어가는 70B 이상의 대형 오픈소스 모델을 쿠버네티스 환경에서 어떻게 쪼개서 서빙하는지 구조를 완벽히 이해합니다.
2. **인프라 레벨의 장애 대응:** 인프라 장애 시 AI 서비스가 먹통이 되지 않고 자동으로 복구되는 클러스터 설계 능력을 갖추게 됩니다.
