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




