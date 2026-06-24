GPU 자원의 낭비를 막고 모니터링하기 위한 관측 가능성 체계입니다.
* NVIDIA DCGM Exporter: GPU 온도, 메모리 사용량, SM(Streaming Multiprocessor) 활용률을 프로메테우스(Prometheus) 포맷으로 수집합니다.
* 대시보드: 그라파나(Grafana)와 연동하여 파드별, 노드별 GPU 효율성을 시각화하고 Karpenter 스케일링 정책의 힌트로 활용합니다.
