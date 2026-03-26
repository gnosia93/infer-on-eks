
쿠버네티스 이벤트(Kubernetes Events)는 클러스터 내에서 무언가 중요한 일(상태 변화, 에러, 라이프사이클 단계 등)이 발생했을 때 이를 기록하고 보고하는 특별한 종류의 리소스 객체이다.
쉽게 말해 쿠버네티스 클러스터의 시스템 로그 또는 알림 창구 같은 역할을 하며, 관리자가 클러스터나 애플리케이션에 무슨 일이 일어나고 있는지 파악할 때 가장 먼저 확인하는 핵심 디버깅 도구이다.

### 1. 이벤트의 주요 특징 ###
* 상태 비저장(Stateless) 알림: 이벤트 자체는 클러스터의 '원하는 상태(Desired State)'를 정의하지 않고 단지 과거에 일어났던 사실을 기록할 뿐니다.
* 짧은 수명 (TTL): 이벤트가 계속 쌓이면 내장 데이터베이스인 etcd의 용량이 가득 차버리기 때문에, 기본적으로 생성된 지 1시간이 지나면 자동으로 삭제된다.
* 컴포넌트들이 직접 발생시킴: kube-scheduler(스케줄링 성공/실패 기록), kubelet(컨테이너 이미지 풀링, 시작, 재시작, OOM 등 기록), kube-controller-manager 등 클러스터를 구성하는 각 컴포넌트가 맡은 역할에 맞게 직접 이벤트를 생성.

### 2. 이벤트의 구조 (주요 속성) ###
* Type (유형): 크게 두 가지로 나된다.
  * Normal: 정상적인 동작 과정 (예: 스케줄링됨, 이미지 다운로드 완료, 컨테이너 시작됨)
  * Warning: 주의가 필요한 예외 상황이나 에러 (예: 이미지 다운로드 실패, 메모리 부족(OOM), 노드 연결 끊김, 볼륨 마운트 실패)
* Reason (이유): 이벤트의 원인 코드 (예: Scheduled, Failed, BackOff, Pulled)
* Message (메시지): 상세한 설명.
* Source (출처): 이 이벤트를 누가 보고했는지 나타낸다. (예: kubelet, default-scheduler)
* Object (대상 객체): 이 이벤트가 어떤 리소스(Pod, Node, Deployment 등)와 관련된 것인지 가리킨다.

### 3. 이벤트 조회 ###
```
kubectl describe pod <파드_이름>     # 파드 레벨
kubectl get events                 # 네임스페이스 레벨   
kubectl get events --sort-by='.metadata.creationTimestamp'     # 발생시간 역순
kubectl get events -A --field-selector type=Warning            # 클러스터 전체
```

### 4. event 로깅 ###

[values.yaml]
```
config:
  logLevel: debug      # 디버그 모드 (정상 작동 확인 후 info로 변경)
  logFormat: json      # 로그를 JSON 형태로 출력

  # 1. 대상지 (Receivers) 설정
  receivers:
    # (A) 디버깅용 확인 (파드 로그(stdout)에 그대로 출력)
    - name: "dump-stdout"
      stdout: {}

    # (B) 영구 보관용 (Loki) - URL 주소와 스트림 라벨 설정
    - name: "loki-db"
      loki:
        # 클러스터 내 Loki의 실제 Push 주소를 적어줍니다.
        # 예: http://<loki-service-name>.<namespace>.svc.cluster.local:<port>/loki/api/v1/push
        url: "http://loki-gateway.monitoring.svc.cluster.local/loki/api/v1/push"
        
        # Grafana에서 이벤트를 쉽게 골라내기 위해 라벨을 붙입니다.
        streamLabels:
          "app": "kubernetes-event-exporter"
          "cluster_name": "ai-gpu-cluster"

    # (C) 즉각 대응용 (Slack Webhook 알림)
    - name: "slack-alert"
      webhook:
        endpoint: "https://hooks.slack.com/services/TXXXXX/BXXXXX/XXXXX" # 슬랙 웹훅 URL
        layout:
          # 슬랙에 표시될 메시지 포맷 커스텀
          text: "🚨 *[K8s Event Warning]*\n*리소스:* `{{ .InvolvedObject.Kind }}/{{ .InvolvedObject.Name }}`\n*이유:* `{{ .Reason }}`\n*메시지:* {{ .Message }}"

  # 2. 필터링 및 분배 (Route) 설정
  route:
    routes:
      # 모든 이벤트를 stdout과 Loki로 보냄
      - match:
          - receiver: "dump-stdout"
          - receiver: "loki-db"
      
      # 단, Slack 알림의 경우 Normal(정상) 이벤트는 무시(drop)하고, Warning(에러)만 전송
      - drop:
          - type: "Normal"
        match:
          - receiver: "slack-alert"
```

[event-exporter 설치]
```
# 1. Bitnami Helm Repository 추가 및 업데이트
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

# 2. Helm Chart 설치 (네임스페이스는 monitoring 앱들이 있는 곳에 맞춤)
helm install event-exporter bitnami/kubernetes-event-exporter \
  --namespace monitoring \
  --create-namespace \
  -f values.yaml


# 1. 파드가 잘 떴는지 확인
kubectl get pods -n monitoring -l app.kubernetes.io/name=kubernetes-event-exporter

# 2. stdout으로 이벤트가 잘 들어오는지 로그 확인 (json 형태로 막 올라오면 성공!)
kubectl logs -f -n monitoring -l app.kubernetes.io/name=kubernetes-event-exporter
```
