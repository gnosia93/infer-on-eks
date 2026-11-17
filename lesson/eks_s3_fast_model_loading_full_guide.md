# EKS 환경에서 S3 모델 가중치 초고속 로딩 실전 가이드 (완전판)

본 문서는 Amazon EKS(Kubernetes) 환경에서 대규모 AI 모델 가중치를 S3로부터 빠르게 로딩하는 **4가지 핵심 아키텍처 패턴**, 각 방식의 **실전 배포용 YAML 예시**, 그리고 이를 운영하기 위한 **최소 권한 IAM Policy JSON** 및 **Karpenter `NodePool`/`EC2NodeClass` 설정 예시**를 포함합니다.

---

## 1. 아키텍처 패턴별 요약 비교

| 방식 | 로딩 시점 | 저장 경로 | Cold Start 속도 | 구현 난이도 | 추천 상황 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Init Container + NVMe** | 파드 스케줄링 시 | S3 → 로컬 NVMe → GPU | 보통 (수십 초) | 낮음 | 모델 크기 20GB 이하, 다양한 모델 유연하게 배포 시 |
| **2. Node Pre-warming** | 노드 부팅 시 (파드 이전) | S3 → 로컬 NVMe → GPU | 매우 빠름 (수 초) | 높음 | 30GB 이상 대형 모델(70B+), 오토스케일링 지연 최소화 |
| **3. S3 Express + Mountpoint** | 파드 실행 시 스트리밍 | S3 Express → 마운트 → GPU | 빠름 (디스크 복사 생략) | 보통 | 단일 AZ 내 초고속 읽기 필요 시, 스토리지 관리 부담 최소화 |
| **4. Run:ai Model Streamer** | 파드 실행 시 직접 적재 | S3 → **GPU VRAM 직행** | 매우 빠름 (디스크 I/O 없음) | 낮음~보통 | vLLM 등 지원 추론 엔진 사용 시, 디스크 공간 절약 및 최고 속도 |

---

## 2. 패턴별 실전 Kubernetes YAML 예시

### 패턴 1: Init Container + NVMe 방식 (파드 스케줄링 시점 복사)
파드가 노드에 할당된 직후 `s5cmd`를 실행해 노드의 로컬 NVMe(`/mnt/nvme` 또는 `emptyDir`)로 모델 가중치를 병렬 다운로드한 뒤 추론 컨테이너를 실행합니다.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: llm-inference-init-nvme
  namespace: ai-inference
spec:
  replicas: 1
  selector:
    matchLabels:
      app: llm-init-nvme
  template:
    metadata:
      labels:
        app: llm-init-nvme
    spec:
      serviceAccountName: model-loader-sa # S3 읽기 권한이 매핑된 IRSA/Pod Identity
      nodeSelector:
        node.kubernetes.io/instance-type: g5.2xlarge # 로컬 NVMe 장착 인스턴스
      initContainers:
        - name: s5cmd-model-downloader
          image: peakcom/s5cmd:v2.2.2
          command: ["/bin/sh", "-c"]
          args:
            - |
              echo "Starting high-speed parallel download from S3..."
              s5cmd --numworkers 64 cp "s3://my-ai-models-bucket/llama-3-70b-safetensors/*" /models/
              echo "Download completed."
          volumeMounts:
            - name: nvme-model-storage
              mountPath: /models
      containers:
        - name: vllm-inference
          image: vllm/vllm-openai:latest
          args:
            - "--model=/models"
            - "--tensor-parallel-size=1"
          resources:
            limits:
              nvidia.com/gpu: 1
          volumeMounts:
            - name: nvme-model-storage
              mountPath: /models
      volumes:
        - name: nvme-model-storage
          hostPath:
            path: /mnt/k8s-disks/0 # EC2 인스턴스 스토어(NVMe) 마운트 경로
            type: DirectoryOrCreate
```

---

### 패턴 2: Node Pre-warming 방식 (노드 부팅 시점 사전 복사)
새 GPU 노드가 생성될 때 Taint(`model-ready=false:NoSchedule`)를 부여해 일반 파드 스케줄링을 차단하고, `DaemonSet`이 노드의 로컬 NVMe에 모델을 미리 다운로드한 뒤 Taint를 제거합니다.

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: node-model-prewarmer
  namespace: kube-system
spec:
  selector:
    matchLabels:
      name: node-model-prewarmer
  template:
    metadata:
      labels:
        name: node-model-prewarmer
    spec:
      serviceAccountName: node-prewarmer-sa # S3 읽기 + Node Taint 제거 권한 필요
      nodeSelector:
        karpenter.sh/nodepool: gpu-inference-pool
      tolerations:
        - key: "model-ready"
          operator: "Equal"
          value: "false"
          effect: "NoSchedule"
        - key: "nvidia.com/gpu"
          operator: "Exists"
          effect: "NoSchedule"
      initContainers:
        - name: download-weights-to-nvme
          image: peakcom/s5cmd:v2.2.2
          command: ["/bin/sh", "-c"]
          args:
            - |
              if [ ! -f /host-nvme/llama-3-70b/.ready ]; then
                mkdir -p /host-nvme/llama-3-70b
                s5cmd --numworkers 64 cp "s3://my-ai-models-bucket/llama-3-70b-safetensors/*" /host-nvme/llama-3-70b/
                touch /host-nvme/llama-3-70b/.ready
              fi
          volumeMounts:
            - name: host-nvme
              mountPath: /host-nvme
        - name: remove-node-taint
          image: bitnami/kubectl:latest
          env:
            - name: NODE_NAME
              valueFrom:
                fieldRef:
                  fieldPath: spec.nodeName
          command: ["/bin/sh", "-c"]
          args:
            - |
              kubectl taint nodes $NODE_NAME model-ready=false:NoSchedule- || true
      containers:
        - name: pause
          image: registry.k8s.io/pause:3.9
      volumes:
        - name: host-nvme
          hostPath:
            path: /mnt/k8s-disks/0
            type: DirectoryOrCreate
```

---

### 패턴 3: S3 Express One Zone + Mountpoint for Amazon S3 CSI
디렉토리 버킷(S3 Express One Zone)과 Mountpoint CSI 드라이버를 결합해 로컬 디스크 복사 과정 없이 초고속 파일 시스템처럼 마운트합니다. *(주의: 디렉토리 버킷과 GPU 노드는 반드시 **동일한 가용 영역(AZ)**에 위치해야 합니다.)*

```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: s3-express-model-pv
spec:
  capacity:
    storage: 1000Gi
  accessModes:
    - ReadOnlyMany
  mountOptions:
    - allow-delete
    - region ap-northeast-2
    - part-size 16777216 # 16MB 청크 단위로 병렬 읽기 최적화
  csi:
    driver: s3.csi.aws.com
    volumeHandle: s3-express-pv-handle
    volumeAttributes:
      bucketName: my-models-bucket--apne2-az1--x-s3 # S3 Express 디렉토리 버킷명
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: s3-express-model-pvc
  namespace: ai-inference
spec:
  accessModes:
    - ReadOnlyMany
  storageClassName: ""
  resources:
    requests:
      storage: 1000Gi
  volumeName: s3-express-model-pv
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: llm-inference-s3-express
  namespace: ai-inference
spec:
  replicas: 2
  selector:
    matchLabels:
      app: llm-s3-express
  template:
    metadata:
      labels:
        app: llm-s3-express
    spec:
      nodeSelector:
        topology.kubernetes.io/zone: ap-northeast-2a # S3 Express 버킷과 동일한 AZ 강제
      containers:
        - name: vllm-inference
          image: vllm/vllm-openai:latest
          args:
            - "--model=/s3-models/llama-3-70b"
          resources:
            limits:
              nvidia.com/gpu: 1
          volumeMounts:
            - name: s3-model-vol
              mountPath: /s3-models
              readOnly: true
      volumes:
        - name: s3-model-vol
          persistentVolumeClaim:
            claimName: s3-express-model-pvc
```

---

### 패턴 4: Run:ai Model Streamer 방식 (S3 → GPU VRAM 직행 스트리밍)
로컬 디스크 I/O나 볼륨 마운트 없이, 추론 엔진(vLLM 등)이 S3 객체 스토리지에서 GPU 메모리로 가중치를 직접 병렬 스트리밍합니다.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: llm-inference-runai-streamer
  namespace: ai-inference
spec:
  replicas: 1
  selector:
    matchLabels:
      app: llm-runai-streamer
  template:
    metadata:
      labels:
        app: llm-runai-streamer
    spec:
      serviceAccountName: model-loader-sa # S3 읽기 권한 필요
      containers:
        - name: vllm-inference
          image: vllm/vllm-openai:latest
          args:
            - "--model=s3://my-ai-models-bucket/llama-3-70b-safetensors/"
            - "--load-format=runai_streamer" # Run:ai Model Streamer 활성화
          env:
            - name: AWS_REGION
              value: "ap-northeast-2"
            - name: RUNAI_STREAMER_CONCURRENCY
              value: "32" # S3 병렬 스트리밍 스레드 수
            - name: RUNAI_STREAMER_CHUNK_SIZE_BYTES
              value: "16777216" # 16MB 단위 스트리밍
          resources:
            limits:
              nvidia.com/gpu: 1
```

---

## 3. 최소 권한 IAM Policy (JSON)

EKS Pod Identity 또는 IRSA(IAM Roles for Service Accounts)에 연결할 최소 권한 정책입니다.

### 3-1. 일반 S3 버킷용 최소 권한 Policy (`s5cmd`, `Run:ai Streamer` 공통)
특정 모델 버킷의 객체 조회 및 목록 확인 권한만 최소한으로 부여합니다.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowListModelBucket",
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket",
        "s3:GetBucketLocation"
      ],
      "Resource": "arn:aws:s3:::my-ai-models-bucket"
    },
    {
      "Sid": "AllowReadModelWeights",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::my-ai-models-bucket/*"
    }
  ]
}
```

### 3-2. S3 Express One Zone 디렉토리 버킷용 최소 권한 Policy (`Mountpoint CSI`용)
S3 Express One Zone은 일반 `s3:*` 액션이 아닌 `s3express:CreateSession` 세션을 통해 인증합니다.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowS3ExpressSession",
      "Effect": "Allow",
      "Action": [
        "s3express:CreateSession"
      ],
      "Resource": "arn:aws:s3express:ap-northeast-2:123456789012:bucket/my-models-bucket--apne2-az1--x-s3"
    }
  ]
}
```
*(참고: `123456789012`는 실제 AWS 계정 ID로 변경해야 합니다.)*

---

## 4. Karpenter `NodePool` 및 `EC2NodeClass` 설정 예시

Karpenter를 사용해 GPU 인스턴스 프로비저닝 시 **로컬 NVMe 인스턴스 스토어를 자동으로 RAID 0으로 묶어 마운트**하고, **노드 부팅 직후 `model-ready=false` Taint를 자동 부여**하는 실전 설정입니다.

```yaml
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: gpu-inference-pool
spec:
  template:
    metadata:
      labels:
        workload-type: ai-inference
    spec:
      # 패턴 2(Node Pre-warming) 사용 시 활성화: 모델 다운로드 완료 전 일반 파드 스케줄링 차단
      startupTaints:
        - key: model-ready
          value: "false"
          effect: NoSchedule
      taints:
        - key: nvidia.com/gpu
          value: "true"
          effect: NoSchedule
      requirements:
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["on-demand", "spot"]
        - key: node.kubernetes.io/instance-type
          operator: In
          values: ["g5.2xlarge", "g5.4xlarge", "g6.2xlarge", "g6.4xlarge"]
        # 패턴 3(S3 Express) 사용 시 버킷과 동일한 AZ로 제한 권장
        - key: topology.kubernetes.io/zone
          operator: In
          values: ["ap-northeast-2a"]
      nodeClassRef:
        group: karpenter.k8s.aws
        kind: EC2NodeClass
        name: gpu-nvme-nodeclass
  limits:
    cpu: "256"
    nvidia.com/gpu: "16"
  disruption:
    consolidationPolicy: WhenEmpty
    consolidateAfter: 300s
---
apiVersion: karpenter.k8s.aws/v1
kind: EC2NodeClass
metadata:
  name: gpu-nvme-nodeclass
spec:
  amiFamily: AL2023 # Amazon Linux 2023 (NVIDIA 드라이버 및 컨테이너 런타임 기본 포함)
  role: "KarpenterNodeRole-my-eks-cluster"
  subnetSelectorTerms:
    - tags:
        karpenter.sh/discovery: "my-eks-cluster"
  securityGroupSelectorTerms:
    - tags:
        karpenter.sh/discovery: "my-eks-cluster"
  # 로컬 인스턴스 스토어(NVMe SSD)를 RAID 0으로 구성해 /mnt/k8s-disks/0 에 자동 마운트
  instanceStorePolicy: RAID0
  blockDeviceMappings:
    - deviceName: /dev/xvda
      ebs:
        volumeSize: 100Gi
        volumeType: gp3
        iops: 3000
        throughput: 125
        deleteOnTermination: true
```

### Karpenter 핵심 포인트
1. **`instanceStorePolicy: RAID0`:** Karpenter가 `g5`, `g6`, `p4d`, `p5` 등에 장착된 로컬 NVMe 디스크를 감지해 자동으로 포맷 후 `/mnt/k8s-disks/0` 경로에 마운트해 줍니다. 별도의 복잡한 부팅 스크립트(`userData`)를 짤 필요가 없습니다.
2. **`startupTaints`:** `taints`와 달리 `startupTaints`는 노드가 처음 생성될 때만 한 번 적용됩니다. 패턴 2의 `DaemonSet`이 NVMe에 모델 다운로드를 마치고 `kubectl taint nodes ... model-ready=false:NoSchedule-`로 제거하면 다시 붙지 않아 추론 파드가 즉시 스케줄링됩니다.
