## EKS ##
Control Plane 로그 활성화 (CloudWatch로 전송)
```
aws eks update-cluster-config --name my-cluster \
  --logging '{"clusterLogging":[{"types":["api","audit","authenticator","controllerManager","scheduler"],"enabled":true}]}'
```
CloudWatch 로그 그룹
```
/aws/eks/my-cluster/cluster
  ├─ kube-apiserver-xxx        → API Server 로그
  ├─ kube-audit-xxx            → 감사 로그 (누가 뭘 했는지)
  ├─ authenticator-xxx         → 인증 로그
  ├─ kube-controller-manager-xxx → Controller Manager 로그
  └─ kube-scheduler-xxx        → Scheduler 로그
```

kube-prometheus-stack 설치하면 API Server 메트릭 Prometheus로 수집할 수 있다.
* apiserver_request_total              API 요청 수
* apiserver_request_duration_seconds   API 응답 시간
* etcd_request_duration_seconds        etcd 응답 시간
* scheduler_scheduling_duration_seconds 스케줄링 소요 시간
```


### 온프램 ###
```
# 직접 로그 확인
journalctl -u kube-apiserver
journalctl -u kube-scheduler
journalctl -u kube-controller-manager
journalctl -u etcd

# etcd 성능 확인
etcdctl endpoint status --write-out=table
etcdctl endpoint health
```

### 대규모에서 주의할 메트릭 ###
* API Server 응답 지연 (느려지면 클러스터 전체 느려짐)

  histogram_quantile(0.99, rate(apiserver_request_duration_seconds_bucket[5m]))

* etcd 쓰기 지연 (10ms 넘으면 위험)

  histogram_quantile(0.99, rate(etcd_disk_wal_fsync_duration_seconds_bucket[5m]))

* 스케줄링 지연

  scheduler_scheduling_duration_seconds
