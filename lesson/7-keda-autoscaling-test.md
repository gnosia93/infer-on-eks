### 부하를 걸어 확인하기 ###

Service(ClusterIP)는 요청 단위가 아니라 TCP 연결 단위로 파드를 고릅니다. 4장의 vllm bench serve는 연결을 재사용하므로, 레플리카가 늘어도 이미 연결된 기존 파드로만 요청을 보냅니다. 그래서 여기서는 요청마다 새 연결을 여는 curl로 부하를 겁니다.







## 레퍼런스 ##

* [KEDA 이벤트 기반 오토스케일링 도입](https://gnobaaaaar.tistory.com/150) 
