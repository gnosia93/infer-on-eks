# Amazon EKS에 Qwen3-32B 배포하기: g6e.12xlarge(L40S × 4), vLLM, Run:ai Model Streamer

AWS 문서 [Load & Serve Models on Amazon EKS](https://docs.aws.amazon.com/eks/latest/userguide/ml-inference-load-serve-model.html)의 흐름을 따르면서 모델을 Qwen3-32B로, 인스턴스를 GPU 4장짜리 g6e.12xlarge로 바꾼 튜토리얼입니다. 모델이 원문보다 6배 크기 때문에 GPU 4장에 나눠 올립니다(TP=4). 로딩과 시작 시간을 줄이는 설정은 [Accelerate model loading on Amazon EKS](https://docs.aws.amazon.com/eks/latest/userguide/ml-inference-fast-model-loading.html)에서 가져왔습니다.

파일 크기는 Hugging Face API에서 확인한 실제 값입니다. "추정"으로 표시한 시간과 메모리 수치는 공개 자료를 이어 붙여 계산한 값이므로 직접 측정해서 확인해야 합니다.

## 전체 구조

```text
Hugging Face (Qwen/Qwen3-32B)
   │  1단계: Kubernetes Job이 파일 단위로 받아서 S3에 올림
   ▼
S3 버킷  s3://<MODEL_BUCKET>/Qwen3-32B/   (safetensors 17개, 65.5 GB)
   │  2단계: Run:ai Model Streamer가 S3에서 GPU 메모리로 바로 스트리밍
   ▼
g6e.12xlarge 노드 1대: vLLM pod 1개 (L40S 4장, TP=4)
   │  ClusterIP Service :8000 (클러스터 내부 전용)
   ▼
3에서 5단계: port-forward로 테스트, Grafana로 모니터링, Open WebUI로 채팅
```

## 원문과 달라진 점

| 항목 | 원문 (Ministral-3-8B) | 이 튜토리얼 (Qwen3-32B) | 이유 |
|---|---|---|---|
| 가중치 | `consolidated.safetensors` 1개, 10.4 GB | safetensors 17개, 65.5 GB (BF16) | 모델 크기 |
| 인스턴스 | NodePool이 고름 (원문 예시는 g6e.4xlarge, GPU 1장) | `g6e.12xlarge`로 고정 | `gpu-inf` NodePool은 g5, g6의 GPU 4장짜리도 허용함. 고정하지 않으면 GPU 메모리가 작은 A10G나 L4 노드가 뜰 수 있음 |
| GPU 수, TP | 1장, TP=1 | 4장, TP=4 | BF16 65.5 GB는 L40S 1장(48 GB)에 안 들어감 |
| `--enforce-eager` | 사용 | 뺌 | distributed streaming과 같이 쓸 수 없음. 기본 모드(torch.compile + CUDA graph)의 처리량이 5에서 30% 높음 |
| Run:ai Streamer | 기본값 | `concurrency` 17, `distributed` true, chunk 4 GiB | AWS 가속 문서 권장값 |
| `/dev/shm` | 설정 없음 | 메모리 볼륨 8 GiB | TP 워커끼리 통신할 때 씀. 컨테이너 기본값 64 MB로는 부족 |
| probe | 없음 | startupProbe, readinessProbe | probe가 없으면 컨테이너가 뜨자마자 1/1이 되어서, 실제로 서빙할 수 있는 시점과 어긋남 |
| compile 캐시 | 없음 | 노드 NVMe에 hostPath로 저장 | 같은 노드에서 다시 뜰 때 compile을 건너뜀 |
| 배포 전략 | RollingUpdate (기본값) | Recreate | 2단계 설명 참고 |
| 파서 | mistral | reasoning `qwen3`, tool `hermes` | Qwen3 권장 설정 |
| 다운로드 Job | 전부 받은 뒤 한꺼번에 업로드 | 파일마다 받고, 올리고, 지움. 이미 올라간 파일은 건너뜀 | 디스크를 약 16 GB만 씀. 실패 후 재시도하면 이어서 진행 |
| Open WebUI | 인증 끔, 인터넷용 ALB(IP 제한) | 인증 켬, port-forward | 아래 보안 메모 참고 |

## 용량 계획: 왜 g6e.12xlarge와 TP=4인가

| 항목 | 값 | 비고 |
|---|---|---|
| g6e.12xlarge | L40S 4장(장당 48 GB), vCPU 48, 메모리 384 GiB, 네트워크 100 Gbps, NVMe 2 × 1900 GB | GPU끼리 NVLink 없이 PCIe로 연결 |
| 가중치 (BF16) | 65,524,328,560 bytes (65.5 GB, 61.0 GiB) | safetensors 17개 합계 |
| GPU당 가중치 (TP=4) | 약 15.3 GiB | 61.0 GiB ÷ 4 |
| GPU당 vLLM 메모리 예산 | 약 40 GiB | 약 45 GiB × `--gpu-memory-utilization 0.90` |
| GPU당 KV 캐시 | 20 GiB 남짓 (추정) | 예산에서 가중치, activation, CUDA graph, 통신 버퍼를 뺀 값 |
| 토큰당 KV 캐시 | 256 KiB (GPU당 64 KiB) | 64층 × KV head 8개 × head_dim 128 × K와 V 2개 × 2 bytes |
| KV 캐시 용량 | 약 30만 토큰대 (추정) | 32,768 토큰짜리 요청이면 약 10개를 동시에 처리 |

TP=2로도 가중치(GPU당 약 30.5 GiB)는 들어갑니다. 하지만 KV 캐시가 GPU당 6 GiB 안팎만 남아 전체 약 5만 토큰(추정)으로 줄어듭니다. 인스턴스에 GPU가 4장 있으니 TP=4로 KV 캐시를 넉넉히 확보합니다.

## 사전 준비

원문과 같은 클러스터와 GPU NodePool을 씁니다. EKS Auto Mode와 자체 관리 Karpenter 모두에서 동작합니다.

- [Set up Amazon EKS cluster for AI/ML workloads](https://docs.aws.amazon.com/eks/latest/userguide/ml-cluster-setup-cli.html): 클러스터, 모니터링 스택, 모델 버킷, `model-storage-sa` 서비스 계정
- [Create a GPU NodePool for AI/ML inference](https://docs.aws.amazon.com/eks/latest/userguide/ml-inference-gpu-nodepool-cli.html): `gpu-inf` NodePool

### 0-1. 환경 변수

```bash
export CLUSTER_NAME=ai-eks-docs
export AWS_REGION=us-east-2
export MODEL_BUCKET=$(aws s3api list-buckets \
  --query "Buckets[?starts_with(Name, '${CLUSTER_NAME}-models-')].Name | [0]" \
  --output text)
```

compile 캐시를 둘 노드 NVMe 경로를 정합니다. EKS Auto Mode라면 다음과 같습니다.

```bash
export COMPILE_CACHE_DIR=/mnt/.ephemeral/compile-cache
```

자체 관리 Karpenter라면 다음 경로를 씁니다. `EC2NodeClass`에 `instanceStorePolicy: RAID0`가 있어야 이 경로가 NVMe에 잡힙니다.

```bash
export COMPILE_CACHE_DIR=/mnt/k8s-disks/0/compile-cache
```

값을 확인합니다. 버킷 이름이 `None`이면 사전 준비의 버킷 단계를 먼저 하세요.

```bash
echo "MODEL_BUCKET=${MODEL_BUCKET}"
echo "COMPILE_CACHE_DIR=${COMPILE_CACHE_DIR}"
```

### 0-2. GPU 쿼터 확인

G 계열 쿼터는 vCPU 단위로 셉니다. g6e.12xlarge 1대에 48이 필요하고, 이미 떠 있는 G 인스턴스 몫이 여기에 더해집니다. `gpu-inf` NodePool은 Spot과 On-Demand를 모두 쓰므로 두 쿼터를 다 확인합니다.

```bash
aws service-quotas get-service-quota --service-code ec2 --quota-code L-DB2E81BA \
  --region ${AWS_REGION} --query 'Quota.[QuotaName,Value]' --output text
aws service-quotas get-service-quota --service-code ec2 --quota-code L-3819A6DF \
  --region ${AWS_REGION} --query 'Quota.[QuotaName,Value]' --output text
```

### 0-3. g6e.12xlarge가 있는 AZ 확인

```bash
aws ec2 describe-instance-type-offerings --region ${AWS_REGION} \
  --location-type availability-zone \
  --filters Name=instance-type,Values=g6e.12xlarge \
  --query 'InstanceTypeOfferings[].Location' --output text
```

클러스터 서브넷이 있는 AZ가 하나 이상 나와야 합니다.

### 0-4. S3 Gateway VPC 엔드포인트 (권장)

노드가 프라이빗 서브넷에 있으면 S3 트래픽이 NAT Gateway를 지납니다. NAT Gateway 대역폭은 서브넷의 모든 노드가 나눠 쓰고, GB당 처리 요금도 붙습니다. pod가 뜰 때마다 65.5 GB를 받으므로 Gateway 엔드포인트를 두는 것이 좋습니다 (AWS 가속 문서 권고).

이미 있는지 확인합니다.

```bash
export VPC_ID=$(aws eks describe-cluster --name ${CLUSTER_NAME} --region ${AWS_REGION} \
  --query 'cluster.resourcesVpcConfig.vpcId' --output text)

aws ec2 describe-vpc-endpoints --region ${AWS_REGION} \
  --filters Name=vpc-id,Values=${VPC_ID} Name=service-name,Values=com.amazonaws.${AWS_REGION}.s3 \
  --query 'VpcEndpoints[].[VpcEndpointId,VpcEndpointType,State]' --output table
```

아무것도 안 나오면 새로 만듭니다. 정리 단계에서 찾을 수 있도록 태그를 붙입니다.

```bash
aws ec2 create-vpc-endpoint --region ${AWS_REGION} \
  --vpc-id ${VPC_ID} \
  --vpc-endpoint-type Gateway \
  --service-name com.amazonaws.${AWS_REGION}.s3 \
  --route-table-ids $(aws ec2 describe-route-tables --region ${AWS_REGION} \
      --filters Name=vpc-id,Values=${VPC_ID} \
      --query 'RouteTables[].RouteTableId' --output text) \
  --tag-specifications 'ResourceType=vpc-endpoint,Tags=[{Key=guide,Value=qwen3-32b-tutorial}]'
```

## 1단계: 모델을 Hugging Face에서 S3로 옮기기

Job 하나가 Qwen3-32B 파일을 4개씩 동시에 받아서 S3에 올리고, 다 올린 파일은 바로 지웁니다. 그래서 디스크는 shard 4개 분량(약 16 GB)만 씁니다. 같은 크기의 파일이 이미 S3에 있으면 건너뛰므로, 중간에 실패해도 Job이 재시도할 때 이어서 진행합니다. Qwen3-32B는 Apache 2.0 라이선스라 Hugging Face 토큰 없이 받을 수 있습니다.

```bash
cat << EOF | kubectl apply -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: qwen3-32b-download
  namespace: default
  labels:
    guide: ai-eks-docs
data:
  download.py: |
    import os
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed

    import boto3
    from boto3.s3.transfer import TransferConfig
    from botocore.exceptions import ClientError
    from huggingface_hub import HfApi, hf_hub_download

    REPO_ID = os.environ["HF_REPO_ID"]
    BUCKET = os.environ["MODEL_BUCKET"]
    PREFIX = os.environ["S3_PREFIX"]
    LOCAL_DIR = "/work/model"

    s3 = boto3.client("s3")
    transfer = TransferConfig(multipart_chunksize=32 * 1024 * 1024, max_concurrency=8)

    files = [
        f for f in HfApi().list_repo_tree(REPO_ID, recursive=True)
        if getattr(f, "size", None) is not None and not f.path.startswith(".")
    ]
    total_gb = sum(f.size for f in files) / 1e9
    print(f"{len(files)} files, {total_gb:.1f} GB: {REPO_ID} -> s3://{BUCKET}/{PREFIX}/", flush=True)

    def already_uploaded(key, size):
        try:
            return s3.head_object(Bucket=BUCKET, Key=key)["ContentLength"] == size
        except ClientError:
            return False

    def copy(f):
        key = f"{PREFIX}/{f.path}"
        if already_uploaded(key, f.size):
            return f"{f.path}: already in S3, skipped"
        start = time.time()
        path = hf_hub_download(REPO_ID, f.path, local_dir=LOCAL_DIR)
        s3.upload_file(path, BUCKET, key, Config=transfer)
        os.remove(path)
        return f"{f.path}: {f.size / 1e9:.2f} GB in {time.time() - start:.0f}s"

    with ThreadPoolExecutor(max_workers=4) as pool:
        for future in as_completed([pool.submit(copy, f) for f in files]):
            print(future.result(), flush=True)

    print("Upload complete", flush=True)
---
apiVersion: batch/v1
kind: Job
metadata:
  name: qwen3-32b-download
  namespace: default
  labels:
    guide: ai-eks-docs
spec:
  backoffLimit: 3
  activeDeadlineSeconds: 7200
  ttlSecondsAfterFinished: 86400
  template:
    metadata:
      labels:
        guide: ai-eks-docs
    spec:
      restartPolicy: Never
      serviceAccountName: model-storage-sa
      containers:
      - name: downloader
        image: python:3.11-slim
        command: ["/bin/bash", "-c"]
        args:
        - "pip install -q huggingface_hub boto3 && python3 /scripts/download.py"
        env:
        - name: HF_REPO_ID
          value: "Qwen/Qwen3-32B"
        - name: MODEL_BUCKET
          value: "${MODEL_BUCKET}"
        - name: S3_PREFIX
          value: "Qwen3-32B"
        - name: AWS_REGION
          value: "${AWS_REGION}"
        - name: HF_HUB_DISABLE_XET
          value: "1"
        resources:
          requests:
            cpu: "2"
            memory: 4Gi
            ephemeral-storage: 30Gi
          limits:
            cpu: "4"
            memory: 8Gi
            ephemeral-storage: 50Gi
        volumeMounts:
        - name: script
          mountPath: /scripts
        - name: work
          mountPath: /work
      volumes:
      - name: script
        configMap:
          name: qwen3-32b-download
      - name: work
        emptyDir:
          sizeLimit: 50Gi
EOF
```

진행 상황을 봅니다. pod가 아직 시작되지 않았다는 메시지가 나오면 몇 초 뒤 다시 실행하세요.

```bash
kubectl logs -f job/qwen3-32b-download
```

첫 줄은 다음과 같고, 이후 파일마다 크기와 걸린 시간이 한 줄씩 찍힙니다. 끝나면 `Upload complete`가 나옵니다.

```text
26 files, 65.5 GB: Qwen/Qwen3-32B -> s3://<버킷 이름>/Qwen3-32B/
```

원문의 10.4 GB가 3에서 5분 걸렸으니 65.5 GB는 15에서 30분 정도로 예상합니다 (추정). 속도는 Job이 뜬 노드의 네트워크와 Hugging Face 쪽 상황에 따라 달라집니다.

```bash
kubectl wait --for=condition=complete job/qwen3-32b-download --timeout=7200s
```

S3에 올라간 파일을 확인합니다.

```bash
aws s3 ls s3://${MODEL_BUCKET}/Qwen3-32B/ --recursive --summarize --human-readable | tail -n 2
```

예상 출력입니다. Hugging Face 저장소가 바뀌면 조금 달라질 수 있습니다.

```text
Total Objects: 26
   Total Size: 61.0 GiB
```

## 2단계: vLLM 배포

GPU 4장을 쓰는 vLLM Deployment와 클러스터 내부용 ClusterIP Service를 만듭니다. 이미지는 원문과 같은 SOCI 지원 vLLM 0.21.0 DLC입니다.

```bash
cat << EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vllm-qwen3-32b
  namespace: default
  labels:
    guide: ai-eks-docs
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: vllm-qwen3-32b
  template:
    metadata:
      labels:
        app: vllm-qwen3-32b
        guide: ai-eks-docs
    spec:
      serviceAccountName: model-storage-sa
      tolerations:
      - key: nvidia.com/gpu
        operator: Exists
        effect: NoSchedule
      nodeSelector:
        karpenter.sh/nodepool: gpu-inf
        node.kubernetes.io/instance-type: g6e.12xlarge
        # karpenter.sh/capacity-type: on-demand    # Spot 중단을 피하려면 주석 해제
      containers:
      - name: vllm
        image: public.ecr.aws/deep-learning-containers/vllm:0.21.0-gpu-py312-cu130-ubuntu22.04-ec2-v1.0-soci
        ports:
        - name: http
          containerPort: 8000
        args:
        - "--model=s3://${MODEL_BUCKET}/Qwen3-32B/"
        - "--served-model-name=qwen3-32b"
        - "--host=0.0.0.0"
        - "--port=8000"
        - "--tensor-parallel-size=4"
        - "--gpu-memory-utilization=0.90"
        - "--max-model-len=32768"                 # Qwen3 기본 컨텍스트 (config 최대값은 40960)
        - "--max-num-seqs=128"
        - "--load-format=runai_streamer"
        - '--model-loader-extra-config={"concurrency":17,"distributed":true}'   # 17 = ceil(65.5 GB / 4 GB)
        - "--reasoning-parser=qwen3"              # 생각 과정을 reasoning 필드로 분리
        - "--enable-auto-tool-choice"
        - "--tool-call-parser=hermes"             # Qwen3 도구 호출 형식
        env:
        - name: AWS_REGION
          value: "${AWS_REGION}"
        - name: RUNAI_STREAMER_CHUNK_BYTESIZE
          value: "4294967296"
        - name: RUNAI_STREAMER_S3_REQUEST_TIMEOUT_MS
          value: "3000"
        - name: RUNAI_STREAMER_S3_LOW_SPEED_LIMIT
          value: "1048576"
        - name: XDG_CACHE_HOME                    # torch.compile 결과를 노드 NVMe에 저장
          value: "/compile-cache"
        - name: TORCHINDUCTOR_CACHE_DIR
          value: "/compile-cache/inductor"
        - name: TRITON_CACHE_DIR
          value: "/compile-cache/triton"
        resources:
          requests:
            cpu: "32"
            memory: 160Gi
            nvidia.com/gpu: "4"
          limits:
            nvidia.com/gpu: "4"
        volumeMounts:
        - name: dshm
          mountPath: /dev/shm
        - name: compile-cache
          mountPath: /compile-cache
        startupProbe:                             # 컨테이너 시작 후 최대 약 10분 기다림
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
          failureThreshold: 60
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          periodSeconds: 5
          timeoutSeconds: 3
      volumes:
      - name: dshm                                # TP 워커 간 통신용 공유 메모리
        emptyDir:
          medium: Memory
          sizeLimit: 8Gi
      - name: compile-cache
        hostPath:
          path: ${COMPILE_CACHE_DIR}
          type: DirectoryOrCreate
---
apiVersion: v1
kind: Service
metadata:
  name: vllm-qwen3-32b
  namespace: default
  labels:
    app: vllm-qwen3-32b
spec:
  type: ClusterIP
  selector:
    app: vllm-qwen3-32b
  ports:
  - name: http
    port: 8000
    targetPort: 8000
    protocol: TCP
EOF
```

설정 몇 가지를 보충합니다.

- **distributed streaming**: 같은 노드의 TP rank 4개가 읽을 가중치 파일을 나눠 맡습니다. TP가 1보다 클 때만 의미가 있고 `--enforce-eager`와 같이 쓸 수 없습니다.
- **Recreate 전략**: 이 pod는 노드의 GPU 4장을 전부 씁니다. 기본값인 RollingUpdate는 새 pod를 먼저 띄우는데(maxSurge 1), 같은 노드에 빈 GPU가 없으므로 g6e.12xlarge가 한 대 더 뜨고 compile 캐시도 쓰지 못합니다. Recreate는 기존 pod를 먼저 지우고 같은 노드에 새 pod를 올립니다. 대신 재시작하는 1에서 2분(추정) 동안 서비스가 멈춥니다.
- **리소스 요청**: CPU 32, 메모리 160 GiB는 이 pod가 노드(48 vCPU, 384 GiB)를 거의 혼자 쓴다는 가정입니다. 메모리에는 Run:ai Streamer의 CPU 버퍼(최신 문서 기준 기본 상한 40 GB)와 TP 워커 4개의 몫이 들어갑니다.
- **비용**: g6e.12xlarge는 us-east-1 On-Demand 기준 시간당 약 $10.49입니다. Spot은 더 싸지만 중단될 수 있습니다.

pod 상태를 지켜봅니다.

```bash
kubectl get pod -l app=vllm-qwen3-32b -w
```

| 상태 | 의미 |
|---|---|
| `0/1 Pending` | g6e.12xlarge 노드를 기다리는 중 |
| `0/1 ContainerCreating` | 이미지 pull 중 (SOCI) |
| `0/1 Running` | vLLM이 가중치 로딩, compile, CUDA graph 캡처를 하는 중 |
| `1/1 Running` | `/health`가 응답함. 서빙 가능 |

노드가 어떤 용량 유형(Spot, On-Demand)으로 어느 AZ에 떴는지 확인합니다.

```bash
kubectl get nodeclaims
kubectl get nodes -l node.kubernetes.io/instance-type=g6e.12xlarge \
  -L karpenter.sh/capacity-type,topology.kubernetes.io/zone
```

### 단계별 시간 확인

pod 이벤트에서 노드와 이미지 단계를 봅니다.

```bash
kubectl describe pod -l app=vllm-qwen3-32b | grep -A 20 "Events:"
```

`Nominated`에서 `Scheduled`까지가 노드 프로비저닝 시간입니다. `Pulled` 줄의 `in N s`가 이미지 pull 시간입니다.

vLLM 로그에서 엔진 단계를 봅니다.

```bash
kubectl logs deploy/vllm-qwen3-32b | grep -E "Model loading took|torch.compile takes|Graph capturing finished|init engine|GPU KV cache size|Maximum concurrency|Application startup complete"
```

| 로그 | 의미 |
|---|---|
| `Model loading took X GiB memory and Y seconds` | 가중치 로딩. X가 GPU당 약 15.3 GiB면 정상 |
| `torch.compile takes N s in total` | compile 시간. 첫 기동이면 수십 초, 캐시가 있으면 수 초 |
| `GPU KV cache size: N tokens` | KV 캐시 용량. 앞의 용량 계획과 비교 |
| `Maximum concurrency for 32,768 tokens per request: N x` | 최대 길이 요청을 동시에 몇 개 처리할 수 있는지 |
| `Graph capturing finished in N secs` | CUDA graph 캡처 시간 |
| `init engine (...) took N seconds` | 엔진 초기화 전체 시간 |
| `Application startup complete` | API 서버 준비 완료 |

TP rank마다 같은 줄이 여러 번 찍힐 수 있고, 정확한 문구는 vLLM 버전에 따라 조금 다를 수 있습니다. `Custom allreduce is disabled` 경고는 NVLink 없이 PCIe로 연결된 GPU가 3장 이상일 때 나옵니다. 이 경우 vLLM은 NCCL로 통신하므로 무시해도 됩니다.

GPU 4장이 모두 잡혔는지 확인합니다.

```bash
kubectl exec deploy/vllm-qwen3-32b -- nvidia-smi --query-gpu=index,name,memory.used,memory.total --format=csv
```

L40S 4장이 보이고 장마다 메모리의 90% 안팎이 사용 중이어야 합니다.

앞서 만든 `vllm_startup_timeline.py`가 있다면 apply 직후 `python vllm_startup_timeline.py -n default -l app=vllm-qwen3-32b --watch`로 실행해서 단계별 시간을 표로 뽑을 수 있습니다.

### 예상 소요 시간 (추정)

| 단계 | 예상 | 근거 |
|---|---|---|
| GPU 노드 프로비저닝 | 30초에서 2분 | 원문 예시는 약 30초. 용량 상황에 따라 다름 |
| 이미지 pull (SOCI, 8.8 GB) | 30에서 50초 | 원문은 g6e.4xlarge(20 Gbps)에서 48.4초 |
| vLLM 프로세스와 TP 워커 4개 기동 | 20에서 40초 | 추정 |
| 가중치 로딩 (65.5 GB) | 10에서 30초 | 원문은 10.4 GB를 약 5초에 읽음(약 2 GB/s). 100 Gbps에서 같은 효율이면 6초 남짓이지만 여유를 둠 |
| torch.compile (첫 기동) | 50에서 60초 | AWS 가속 문서에서 60 GB 모델이 약 53초. GPU 종류가 다르면 달라짐 |
| KV 캐시 할당, CUDA graph 캡처 | 15에서 40초 | 추정 |

| 상황 | 합계 (추정) |
|---|---|
| 노드는 이미 있고 이미지와 compile 캐시가 없음 | 약 2에서 4분 |
| 새 노드부터 시작 | 약 3에서 6분 |
| 같은 노드에서 재시작 (이미지와 compile 캐시가 있음) | 약 1에서 2분 |

## 3단계: 추론 테스트

vLLM Service를 내 PC로 포워딩합니다. port-forward는 기본으로 127.0.0.1에만 열립니다.

```bash
kubectl port-forward svc/vllm-qwen3-32b 8000:8000
```

새 터미널에서 상태와 모델 이름을 확인합니다. `200`과 `"qwen3-32b"`가 나와야 합니다.

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/health
curl -s http://localhost:8000/v1/models | jq '.data[].id'
```

`jq`가 없으면 `brew install jq`로 설치합니다.

thinking을 끄고 질문합니다. Qwen 권장 샘플링 값(non-thinking: temperature 0.7, top_p 0.8)을 씁니다.

```bash
curl -s http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "qwen3-32b",
    "messages": [{"role": "user", "content": "GPU 노드 오토스케일링에서 요청 대기열 길이를 트리거로 쓰는 이유를 두 문장으로 설명해 줘."}],
    "max_tokens": 300,
    "temperature": 0.7,
    "top_p": 0.8,
    "chat_template_kwargs": {"enable_thinking": false}
  }' | jq -r '.choices[0].message.content'
```

thinking을 켠 기본 동작도 확인합니다 (권장값: temperature 0.6, top_p 0.95). 생각 과정은 `reasoning` 필드에, 답은 `content` 필드에 따로 들어옵니다. 예전 vLLM에서는 이 필드 이름이 `reasoning_content`였습니다.

```bash
curl -s http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "qwen3-32b",
    "messages": [{"role": "user", "content": "17 곱하기 23은 얼마야?"}],
    "max_tokens": 2048,
    "temperature": 0.6,
    "top_p": 0.95
  }' | jq '{reasoning: .choices[0].message.reasoning, content: .choices[0].message.content}'
```

TTFT를 잴 때는 thinking을 신경 써야 합니다. thinking이 켜져 있으면 스트리밍에서 생각 토큰이 `delta.reasoning`으로 먼저 나옵니다. 앞서 만든 `loadtest.py`처럼 `delta.content`의 첫 조각을 기준으로 재면, 생각이 끝난 뒤의 시간이 TTFT로 잡힙니다. 부하 테스트 때는 요청에 `"chat_template_kwargs": {"enable_thinking": false}`를 넣거나, `reasoning` 조각도 첫 토큰으로 세도록 고치세요.

## 4단계: 모니터링

원문과 같이 ServiceMonitor를 만들어 Prometheus가 vLLM 지표를 수집하게 합니다. 클러스터 설정의 모니터링 단계가 먼저 끝나 있어야 합니다.

```bash
cat << 'EOF' | kubectl apply -f -
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: vllm-qwen3-32b
  namespace: default
  labels:
    release: kube-prometheus-stack
spec:
  selector:
    matchLabels:
      app: vllm-qwen3-32b
  endpoints:
  - port: http
    path: /metrics
    interval: 15s
EOF
```

### 트래픽 만들기

vLLM pod 안에서 `vllm bench serve`를 실행합니다. `/v1/completions`를 쓰면 chat template과 reasoning parser를 거치지 않으므로 thinking 설정과 상관없이 토큰 수가 일정합니다. 토크나이저 파일(약 16 MB)은 Hugging Face에서 받습니다.

```bash
kubectl exec deploy/vllm-qwen3-32b -- vllm bench serve \
  --backend openai \
  --endpoint /v1/completions \
  --base-url http://127.0.0.1:8000 \
  --model qwen3-32b \
  --tokenizer Qwen/Qwen3-32B \
  --dataset-name random \
  --random-input-len 1000 \
  --random-output-len 256 \
  --num-prompts 200 \
  --max-concurrency 32 \
  --ignore-eos \
  --percentile-metrics ttft,tpot,itl,e2el \
  --metric-percentiles 50,95,99
```

벤치 클라이언트가 서빙 pod의 CPU를 조금 나눠 쓰므로, 정밀하게 측정할 때는 별도 클라이언트에서 돌리세요.

### Grafana 대시보드

Grafana를 포워딩하고 관리자 비밀번호를 확인합니다.

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3000:80
```

```bash
kubectl --namespace monitoring get secrets kube-prometheus-stack-grafana \
  -o jsonpath="{.data.admin-password}" | base64 -d ; echo
```

http://localhost:3000 에 `admin`으로 로그인합니다. 그다음 **Dashboards > GPU Monitoring > vLLM Metrics**를 엽니다. 같은 폴더의 **NVIDIA DCGM Exporter Dashboard**에서는 GPU 4장의 사용률과 메모리를 볼 수 있습니다.

3단계의 port-forward가 열려 있으면 원시 지표도 바로 볼 수 있습니다.

```bash
curl -s http://localhost:8000/metrics | grep -E '^vllm:(num_requests|kv_cache|gpu_cache)'
```

오토스케일링 트리거로는 `num_requests_waiting`(대기열 길이)을 1순위로, KV 캐시 사용률을 보조로 씁니다.

## 5단계: 채팅 앱 (Open WebUI)

원문과 같은 Open WebUI를 쓰되 인증을 켜고 클러스터 내부 Service로만 둡니다.

```bash
cat << 'EOF' | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: open-webui
  namespace: default
  labels:
    app: open-webui
    guide: ai-eks-docs
spec:
  replicas: 1
  selector:
    matchLabels:
      app: open-webui
  template:
    metadata:
      labels:
        app: open-webui
        guide: ai-eks-docs
    spec:
      containers:
      - name: open-webui
        image: ghcr.io/open-webui/open-webui:v0.9.2
        ports:
        - containerPort: 8080
        resources:
          requests:
            cpu: "500m"
            memory: "500Mi"
          limits:
            cpu: "1000m"
            memory: "2Gi"
        env:
        - name: OPENAI_API_BASE_URLS
          value: "http://vllm-qwen3-32b:8000/v1"
        - name: OPENAI_API_KEY
          value: "dummy"
        - name: WEBUI_AUTH
          value: "True"
        - name: ENABLE_OLLAMA_API
          value: "False"
        - name: ENABLE_EVALUATION_ARENA_MODELS
          value: "False"
        - name: RAG_EMBEDDING_ENGINE
          value: ""
        volumeMounts:
        - name: webui-volume
          mountPath: /app/backend/data
      volumes:
      - name: webui-volume
        emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: open-webui
  namespace: default
  labels:
    app: open-webui
spec:
  type: ClusterIP
  selector:
    app: open-webui
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8080
EOF
```

`OPENAI_API_KEY`는 vLLM에 API 키를 걸지 않았기 때문에 아무 값이나 넣어도 됩니다.

```bash
kubectl wait --for=condition=ready pod -l app=open-webui --timeout=300s
kubectl port-forward svc/open-webui 8080:80
```

http://localhost:8080 에서 처음 만든 계정이 관리자가 됩니다. 모델 목록에서 `qwen3-32b`를 고르면 됩니다. 데이터를 emptyDir에 저장하므로 pod가 다시 뜨면 계정과 대화 기록이 사라집니다.

## 6단계 (선택): 같은 노드 재시작으로 캐시 효과 확인

재시작 전후로 NODE 열이 같은지 확인합니다. 다른 노드에 뜨면 캐시가 없습니다.

```bash
kubectl get pod -l app=vllm-qwen3-32b -o wide
kubectl rollout restart deployment/vllm-qwen3-32b
kubectl get pod -l app=vllm-qwen3-32b -o wide -w
```

새 pod가 Ready가 되면 이미지와 compile 캐시를 썼는지 확인합니다.

```bash
kubectl describe pod -l app=vllm-qwen3-32b | grep -E "Pulled|already present"
kubectl logs deploy/vllm-qwen3-32b | grep -E "Directly load|torch.compile takes|Model loading took"
```

`already present on machine`이 나오면 이미지 pull을 건너뛴 것입니다. `Directly load`가 나오고 compile 시간이 수 초로 줄었으면 compile 캐시를 쓴 것입니다. 가중치는 매번 S3에서 다시 읽습니다.

## 문제 해결

| 증상 | 확인할 것 | 조치 |
|---|---|---|
| pod가 계속 `Pending` | `kubectl get nodeclaims`, `kubectl describe nodeclaim <이름>`, pod 이벤트 | 쿼터(0-2)와 AZ(0-3) 확인. Spot 용량이 없으면 On-Demand로 고정 |
| `0/1 Running`에서 재시작 반복 | `kubectl describe pod`의 `Startup probe failed`, `kubectl logs --previous deploy/vllm-qwen3-32b` | 원인(S3 경로, 메모리 등)을 먼저 확인하고, 로딩이 정말 10분을 넘으면 `failureThreshold`를 늘림 |
| S3 `AccessDenied` | vLLM 로그 | `serviceAccountName: model-storage-sa`와 Pod Identity 연결 확인 |
| NCCL 오류, shared memory 관련 메시지 | vLLM 로그 | `/dev/shm` 볼륨이 붙었는지 확인 |
| `CUDA out of memory` | vLLM 로그 | `--max-model-len`이나 `--max-num-seqs`를 줄임 |
| 가중치 로딩이 수 분 걸림 | `Model loading took` 줄 | S3 Gateway 엔드포인트(0-4)와 `distributed` 설정 확인 |
| 답이 `content`가 아닌 `reasoning`에만 나옴 | 응답 JSON | thinking 모드에서는 정상. 끄려면 `enable_thinking: false`. 끈 뒤에도 스트리밍에서 그러면 vLLM 이슈 #40816 참고 |

## 보안 메모

- vLLM API에는 인증이 없습니다. Service는 ClusterIP로 두고 LoadBalancer, NodePort, Ingress로 직접 공개하지 마세요. 클러스터 안의 다른 pod는 이 API를 호출할 수 있습니다.
- `--host=0.0.0.0`은 pod 안에서 Service 트래픽을 받기 위한 설정입니다. 노드 밖으로 포트를 열지는 않습니다.
- port-forward는 내 PC의 127.0.0.1에만 열립니다. `--address 0.0.0.0`은 쓰지 마세요.
- `model-storage-sa`에는 S3 쓰기와 삭제 권한도 있습니다. 운영에서는 vLLM용으로 읽기 전용 서비스 계정을 따로 만드세요 (클러스터 설정 문서의 권고).
- 원문은 Open WebUI 인증을 끄고 인터넷용 ALB로 공개합니다. 그러면 IP 제한을 통과한 누구나 로그인 없이 GPU를 쓸 수 있어서 이 튜토리얼에서는 그 단계를 뺐습니다.

## 정리

워크로드를 지웁니다.

```bash
kubectl delete deployment,service open-webui --ignore-not-found
kubectl delete servicemonitor vllm-qwen3-32b --ignore-not-found
kubectl delete deployment,service vllm-qwen3-32b --ignore-not-found
kubectl delete job,configmap qwen3-32b-download --ignore-not-found
```

g6e.12xlarge 노드가 목록에서 사라졌는지 확인합니다. 빈 노드는 Karpenter가 정리합니다.

```bash
kubectl get nodeclaims
```

S3의 모델 파일도 지우려면 다음을 실행합니다. 남겨 두면 S3 Standard 기준 월 1.5달러 정도입니다.

```bash
aws s3 rm s3://${MODEL_BUCKET}/Qwen3-32B/ --recursive
```

0-4에서 Gateway 엔드포인트를 새로 만들었다면 태그로 찾아서 지웁니다. 클러스터를 지울 계획이라면 이 엔드포인트를 먼저 지우세요. 남아 있으면 VPC 삭제가 막힐 수 있습니다.

```bash
aws ec2 delete-vpc-endpoints --region ${AWS_REGION} \
  --vpc-endpoint-ids $(aws ec2 describe-vpc-endpoints --region ${AWS_REGION} \
      --filters Name=tag:guide,Values=qwen3-32b-tutorial \
      --query 'VpcEndpoints[].VpcEndpointId' --output text)
```

## 더 해볼 것

- `Qwen/Qwen3-32B-FP8`(34.3 GB): L40S는 FP8을 지원합니다. 가중치가 절반이라 KV 캐시를 늘리거나, TP=2 replica 2개로 나눠 처리량을 비교해 볼 수 있습니다.
- 오토스케일링: `vllm:num_requests_waiting`을 KEDA나 HPA 트리거로 씁니다. 새 노드부터 서빙까지 3에서 6분(추정)이 걸리므로 임계값을 일찍 잡습니다.
- 노드 간 compile 캐시: AWS 가속 문서처럼 compile 결과(약 15 MB)를 S3에 올려 두고 새 노드에서 미리 받습니다.

## 참고 자료

- [Load & Serve Models on Amazon EKS](https://docs.aws.amazon.com/eks/latest/userguide/ml-inference-load-serve-model.html) (원문)
- [Accelerate model loading on Amazon EKS](https://docs.aws.amazon.com/eks/latest/userguide/ml-inference-fast-model-loading.html): Run:ai 튜닝, distributed와 `--enforce-eager`, compile 캐시, S3 Gateway 엔드포인트
- [Create a GPU NodePool using CLIs](https://docs.aws.amazon.com/eks/latest/userguide/ml-inference-gpu-nodepool-cli.html): `gpu-inf` NodePool 조건
- [Set up Amazon EKS cluster for AI/ML workloads using CLIs](https://docs.aws.amazon.com/eks/latest/userguide/ml-cluster-setup-cli.html): 모델 버킷, `model-storage-sa`
- [Qwen3-32B 파일 목록](https://huggingface.co/api/models/Qwen/Qwen3-32B/tree/main), [config.json](https://huggingface.co/Qwen/Qwen3-32B/raw/main/config.json)
- [vLLM 레시피: Qwen3-32B](https://recipes.vllm.ai/Qwen/Qwen3-32B), [Qwen 문서: vLLM 배포](https://qwen.readthedocs.io/en/latest/deployment/vllm.html)
- [vLLM: Reasoning Outputs](https://docs.vllm.ai/en/stable/features/reasoning_outputs/), [vLLM: Kubernetes 배포](https://docs.vllm.ai/en/stable/deployment/k8s/), [vLLM: Run:ai Model Streamer](https://docs.vllm.ai/en/stable/models/extensions/runai_model_streamer/)
- [Run:ai Model Streamer 환경 변수](https://github.com/run-ai/runai-model-streamer/blob/master/docs/src/env-vars.md)
- [g6e.12xlarge 가격](https://instances.usage.ai/aws/ec2/g6e.12xlarge)
- [vLLM 이슈 #40816](https://github.com/vllm-project/vllm/issues/40816)

※ 출처 내용은 라이선스 제한에 맞춰 요약·재구성했습니다.



## 레퍼런스 ##

* https://huggingface.co/Qwen/Qwen3-32B
* https://docs.aws.amazon.com/eks/latest/userguide/ml-inference-load-serve-model.html 
