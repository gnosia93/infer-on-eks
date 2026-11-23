### 인프런스 아키텍처 ###
* alb -> litellm 파드 로 ip routing
* litellm 파드의 경우 2개로 시작해서 hpa 로 자동 스케일링 됨
* deployment 는 text 처리용과 이미지 생성용 두개의 그룹이 있고, 각각 keda + prometheus 메트릭 기반으로 오토 스케일링
* text 는 Gemma 4 26B, 이미지는 Z-Image Turbo (6B) 모델 사용.
* litellm 은 bedrock 으로 fallback 설정. 최초 text 및 이미지 pod 가 5% 정도의 트래픽 처리 -> 향후 100% 까지 canary.
* 클라리언트는 세션 id 를 가지고 요청함.
* litellm 은 랑데뷰 해싱 알고리즘을 이용하여 세션 id 가 동일한 경우 동일 vllm pod 로 트래픽을 라우팅, vllm pod 추가/삭제시에도 정상 동작.
* vllm 으로 text 및 이미지 모델 서빙 / prefix caching 사용.
* 이미지 생성 요청은 SQS 에 요청을 기록.
* rate limit / 장애감지 공유 및  응답 캐싱 (Exact Match Caching) 공유 용도로 elasticache 적용.
* gpu 노드풀은 text 모델용 g7e, 이미지용 g6e 두개로 운용.
* 모델 웨이트는 s3 에 저장하고 run.ai model streamer 를 활용하여 읽어들임
* sqs, bedrock, s3 는 eks 클러스터 외부에 위치
* EKS Node Monitoring Agent와 자동 노드 복구(Node Auto-Repair) 을 이용하여 gpu 노드 장애 감지 및 복구
* promethus 는 gpu 의 xid, temperature, sm activity 및 ecc 정보를 수집.



### llm-d 확장 (Prefill 과 Decode 의 분리) ###
현재 아키텍처(ALB + LiteLLM + Envoy + vLLM)는 별도의 무거운 분산 추론 플랫폼 없이 기존 Kubernetes와 AWS 표준 컴포넌트만으로 멀티턴 성능과 고가용성을 모두 확보할 수 있는 최적 및 최소의 아키텍처다. 향후 대규모 트래픽 대응을 위해 llm-d를 도입하게 될 경우, 다음과 같은 추가 구성과 이점이 따른다.
• 추가 필요 요소: Kubernetes Gateway API(추론 확장), LeaderWorkerSet 등 전용 컨트롤 플레인 설치와 노드 간 고속 KV Cache 전송을 위한 네트워크/캐시 스토리지 구성.
• 도입 시 장점: 각 파드의 실시간 GPU 캐시 상태를 직접 인식해 라우팅하고, 연산(Prefill)과 생성(Decode) 노드를 분리 운영할 수 있어 초장문 컨텍스트 및 대규모 AI 에이전트 환경에서 GPU 처리량을 극대화할 수 있다.

Prefill(입력 처리)은 GPU 연산력을, Decode(토큰 생성)는 메모리 대역폭을 주로 사용하는 정반대의 자원 특성을 가집니다. 따라서 일반적인 챗봇 환경에서는 통합 운영이 유리하며, 수만~10만 토큰 이상의 방대한 문서를 동시에 입력받아 긴 입력 처리가 전체 답변 생성 속도를 지연시키는 초대규모·초장문 환경에서만 두 단계의 분리를 고려한다.


