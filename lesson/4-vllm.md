### 환경 설정 ###
```
export AWS_REGION=$(aws ec2 describe-availability-zones --query 'AvailabilityZones[0].RegionName' --output text)
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export CLUSTER_NAME="infer-on-eks"
export K8S_VERSION="1.34"
export KARPENTER_VERSION="1.8.1"
export VPC_ID=$(aws ec2 describe-vpcs --filters Name=tag:Name,Values="${CLUSTER_NAME}" --query "Vpcs[].VpcId" --output text)

echo "Cluster Name: $AWS_REGION"
echo "AWS Account ID: $AWS_ACCOUNT_ID"
echo "Cluster Name: $CLUSTER_NAME"
echo "EKS Version: $K8S_VERSION"
echo "Karpenter Version: $KARPENTER_VERSION"
echo "VPC ID: $VPC_ID"
```

### 1. S3 버킷 생성 ###

모델 가중치를 저장할 S3 버킷을 생성한다. 
```
export BUCKET="${CLUSTER_NAME:?}-${AWS_ACCOUNT_ID:?}"

# 버킷 생성 (us-east-1 외 리전은 LocationConstraint가 필요합니다)
aws s3api create-bucket \
  --bucket "$BUCKET" \
  --region "$AWS_REGION" \
  --create-bucket-configuration LocationConstraint="$AWS_REGION"

# 생성 확인
aws s3api head-bucket --bucket "$BUCKET"
```

### 2. 모델 업로드 ###

허깅페이스에서 [gemma 모델](https://huggingface.co/RedHatAI/gemma-4-12B-it-FP8-Dynamic) 체크포인트를 받아 S3에 업로드 한다.
```
COMMIT_SHA=$(curl -s https://huggingface.co/api/models/RedHatAI/gemma-4-12B-it-FP8-Dynamic | jq -r .sha)
echo "${COMMIT_SHA}"

hf download RedHatAI/gemma-4-12B-it-FP8-Dynamic \
  --revision "${COMMIT_SHA:?}" \
  --local-dir ./gemma-4-12B-it-FP8-Dynamic
```

[결과]
```
Downloading bytes:                                                                                                            |  0.00B            Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable higher rate limits and faster downloads.          
Fetching 10 files: 100%|██████████████████████████████████████████████████████████████████████████████████████████| 10/10 [01:29<00:00,  8.97s/it]
Download complete: ███████████████████████████████████████████████████████████████████████████████████████████████████████████| 13.6GB, 68.2MB/s  ✓ Downloadedion complete: 100%|███████████████████████████████████████████████████████████████████████████████████████| 15.1GB / 15.1GB,  163MB/s  
  path: /home/ec2-user/gemma-4-12B-it-FP8-Dynamic
Download complete: ███████████████████████████████████████████████████████████████████████████████████████████████████████████| 13.6GB, 68.2MB/s  
Reconstruction complete: 100%|███████████████████████████████████████████████████████████████████████████████████████| 15.1GB / 15.1GB,  163MB/s  
```
s3 에 업로드 한다.
```
aws s3 sync ./gemma-4-12B-it-FP8-Dynamic \
  "s3://${BUCKET:?}/models/gemma-4-12B-it-FP8-Dynamic" \
  --exclude ".cache/*"
```

[결과]
```
upload: gemma-4-12B-it-FP8-Dynamic/.gitattributes to s3://infer-on-eks-499514681453/models/gemma-4-12B-it-FP8-Dynamic/.gitattributes
upload: gemma-4-12B-it-FP8-Dynamic/generation_config.json to s3://infer-on-eks-499514681453/models/gemma-4-12B-it-FP8-Dynamic/generation_config.json
upload: gemma-4-12B-it-FP8-Dynamic/processor_config.json to s3://infer-on-eks-499514681453/models/gemma-4-12B-it-FP8-Dynamic/processor_config.json
upload: gemma-4-12B-it-FP8-Dynamic/chat_template.jinja to s3://infer-on-eks-499514681453/models/gemma-4-12B-it-FP8-Dynamic/chat_template.jinja
upload: gemma-4-12B-it-FP8-Dynamic/README.md to s3://infer-on-eks-499514681453/models/gemma-4-12B-it-FP8-Dynamic/README.md
upload: gemma-4-12B-it-FP8-Dynamic/recipe.yaml to s3://infer-on-eks-499514681453/models/gemma-4-12B-it-FP8-Dynamic/recipe.yaml
upload: gemma-4-12B-it-FP8-Dynamic/tokenizer_config.json to s3://infer-on-eks-499514681453/models/gemma-4-12B-it-FP8-Dynamic/tokenizer_config.json
upload: gemma-4-12B-it-FP8-Dynamic/config.json to s3://infer-on-eks-499514681453/models/gemma-4-12B-it-FP8-Dynamic/config.json
upload: gemma-4-12B-it-FP8-Dynamic/tokenizer.json to s3://infer-on-eks-499514681453/models/gemma-4-12B-it-FP8-Dynamic/tokenizer.json
Completed 5.5 GiB/14.0 GiB (695.1 MiB/s) with 1 file(s) remaining  
```


### 3. IRSA 역할과 서비스 어카운트 만들기 ###
```
# 1. 정책 파일 만들기
cat > gemma-s3-read-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::${BUCKET:?}",
      "Condition": {
        "StringLike": {
          "s3:prefix": [
            "models/gemma-4-12B-it-FP8-Dynamic",
            "models/gemma-4-12B-it-FP8-Dynamic/*"
          ]
        }
      }
    },
    {
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::${BUCKET}/models/gemma-4-12B-it-FP8-Dynamic/*"
    }
  ]
}
EOF
cat gemma-s3-read-policy.json         # Resource에 실제 버킷 이름이 들어갔는지 확인

# 2. IAM 정책 만들기
POLICY_ARN=$(aws iam create-policy \
  --policy-name "${CLUSTER_NAME}-gemma-s3-read" \
  --policy-document file://gemma-s3-read-policy.json \
  --query Policy.Arn --output text)
echo "$POLICY_ARN"

# 3. IRSA 역할과 서비스 어카운트 만들기
eksctl create iamserviceaccount \
  --cluster "${CLUSTER_NAME}" \
  --namespace llm-serving \
  --name vllm-model-reader \
  --role-name "${CLUSTER_NAME}-gemma-s3-read" \
  --attach-policy-arn "${POLICY_ARN}" \
  --approve

# 4. 서비스 어카운트에 역할이 연결됐는지 확인
kubectl get sa vllm-model-reader -n llm-serving \
  -o jsonpath='{.metadata.annotations.eks\.amazonaws\.com/role-arn}'

# 5. 테스트 파드로 S3 읽기 확인
kubectl run s3-test -n llm-serving --rm -it --restart=Never \
  --image=public.ecr.aws/aws-cli/aws-cli \
  --overrides='{"spec":{"serviceAccountName":"vllm-model-reader"}}' \
  -- s3 ls "s3://${BUCKET}/models/gemma-4-12B-it-FP8-Dynamic/"
```
eksctl이 OIDC 신뢰 정책을 가진 IAM 역할을 만들고, 그 역할 ARN이 annotation으로 붙은 쿠버네티스 서비스 어카운트까지 한 번에 만들어 준다. 클러스터에 withOIDC: true가 켜져 있으니 바로 쓸 수 있다. 네임스페이스가 아직 없으면 eksctl이 만든다.

### 4. vLLM 디플로이먼트 생성 ###
파드, 디플로이먼트 및 서비스를 생성한다.
```
kubectl apply -f - <<EOF
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: gemma4-12b-vllm
  namespace: llm-serving
  labels:
    app.kubernetes.io/name: gemma4-12b-vllm
    app.kubernetes.io/component: text-inference
spec:
  replicas: 1
  revisionHistoryLimit: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1                   # 새 파드가 Ready가 된 뒤 기존 파드를 내림 (교체 중 GPU 노드 1대 추가)
      maxUnavailable: 0
  selector:
    matchLabels:
      app.kubernetes.io/name: gemma4-12b-vllm
  template:
    metadata:
      labels:
        app.kubernetes.io/name: gemma4-12b-vllm
        app.kubernetes.io/component: text-inference
    spec:
      serviceAccountName: vllm-model-reader
      terminationGracePeriodSeconds: 120
      nodeSelector:
        karpenter.sh/nodepool: gpu
        node.kubernetes.io/instance-type: g6e.4xlarge
      tolerations:
        - key: nvidia.com/gpu
          operator: Exists
          effect: NoSchedule
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname       # 레플리카를 늘리면 파드를 서로 다른 노드에 배치
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app.kubernetes.io/name: gemma4-12b-vllm
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone  # 가능하면 서로 다른 AZ에 배치
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels:
              app.kubernetes.io/name: gemma4-12b-vllm
      securityContext:
        runAsNonRoot: true
        runAsUser: 2000                             # vLLM 이미지에 내장된 vllm 사용자
        runAsGroup: 0
        fsGroup: 0
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: vllm
          image: vllm/vllm-openai:v0.33.0           # 0.23.0 이상 필요. 운영에서는 @sha256 다이제스트로 고정
          command: ["vllm", "serve"]
          args:
            - s3://${BUCKET:?}/models/gemma-4-12B-it-FP8-Dynamic
            - --load-format=runai_streamer          # S3에서 GPU 메모리로 바로 스트리밍
            - '--model-loader-extra-config={"concurrency":4}'
            - --served-model-name=gemma-4-12b
            - --kv-cache-dtype=fp8                  # KV 캐시도 8비트 (메모리 약 50% 절감)
            - --max-model-len=32768
            - --enable-prefix-caching
            - --reasoning-parser=gemma4
            - '--limit-mm-per-prompt={"image":4,"audio":0}'   # 오디오는 vllm[audio] 추가 설치가 필요해 끔
            - --host=0.0.0.0
            - --port=8000
          env:
            - name: AWS_REGION
              value: ${AWS_REGION:?}
            - name: AWS_DEFAULT_REGION
              value: ${AWS_REGION}
            - name: HF_HUB_OFFLINE                  # Hugging Face 접속 차단. 모든 파일을 S3에서 읽음
              value: "1"
            - name: RUNAI_STREAMER_CHUNK_BYTESIZE   # 4GiB 청크 (AWS 권장값)
              value: "4294967296"
            - name: RUNAI_STREAMER_S3_REQUEST_TIMEOUT_MS
              value: "3000"
            - name: RUNAI_STREAMER_S3_LOW_SPEED_LIMIT
              value: "1048576"
            - name: XDG_CACHE_HOME
              value: /home/vllm/.cache
            - name: TRITON_CACHE_DIR
              value: /home/vllm/.cache/triton
          ports:
            - name: http                            # OpenAI 호환 API와 /metrics 공용 포트
              containerPort: 8000
              protocol: TCP
          resources:                                # g6e.4xlarge(16 vCPU, 128GiB, L40S 48GB) 기준
            requests:
              cpu: "12"
              memory: 80Gi
              nvidia.com/gpu: "1"
            limits:
              memory: 80Gi
              nvidia.com/gpu: "1"
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop: ["ALL"]
          startupProbe:                             # S3 스트리밍 + torch.compile + CUDA graph 캡처 (최대 15분)
            httpGet:
              path: /health
              port: http
            periodSeconds: 10
            failureThreshold: 90
          readinessProbe:                           # Ready인 파드만 서비스 트래픽을 받음
            httpGet:
              path: /health
              port: http
            periodSeconds: 5
            timeoutSeconds: 3
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /health
              port: http
            periodSeconds: 15
            timeoutSeconds: 5
            failureThreshold: 4
          lifecycle:
            preStop:                                # 서비스 엔드포인트에서 빠질 시간을 준 뒤 종료
              exec:
                command: ["sleep", "20"]
          volumeMounts:
            - name: dshm
              mountPath: /dev/shm
            - name: cache
              mountPath: /home/vllm/.cache
      volumes:
        - name: dshm                                # PyTorch 프로세스 간 공유 메모리
          emptyDir:
            medium: Memory
            sizeLimit: 8Gi
        - name: cache                               # 설정 파일, torch.compile·Triton 캐시
          emptyDir:
            sizeLimit: 20Gi
---
apiVersion: v1
kind: Service
metadata:
  name: gemma4-12b-vllm
  namespace: llm-serving
  labels:
    app.kubernetes.io/name: gemma4-12b-vllm
spec:
  type: ClusterIP
  publishNotReadyAddresses: false
  selector:
    app.kubernetes.io/name: gemma4-12b-vllm
  ports:
    - name: http
      port: 8000
      targetPort: http
      protocol: TCP
EOF
```

### vLLM 파드의 emptyDir 볼륨 (dshm, cache) ###

#### emptyDir ####

emptyDir은 파드가 노드에 배치될 때 빈 디렉터리로 만들어지고, 파드가 삭제되면 함께 지워지는 임시 볼륨이다. 같은 파드 안에서 컨테이너가 죽었다가 다시 시작하면 데이터가 남아 있다. 롤링 업데이트나 노드 교체로 파드가 새로 만들어지면 빈 상태로 시작한다.

#### dshm: 공유 메모리 늘리기 ####

- `/dev/shm`은 프로세스끼리 메모리를 공유할 때 쓰는 경로다. PyTorch와 vLLM은 프로세스 사이에 데이터를 넘길 때 이곳을 쓰고, GPU 여러 개로 텐서 병렬을 하면 특히 많이 쓴다.
- 컨테이너의 `/dev/shm`은 기본이 64MB라서 부족하면 `Bus error`나 `No space left on device`로 프로세스가 죽는다. Kubernetes에는 Docker의 `--shm-size` 같은 옵션이 없어서, 메모리 기반 emptyDir을 `/dev/shm`에 마운트하는 방법으로 크기를 늘린다.
- `medium: Memory`는 디스크 대신 RAM(tmpfs)에 만든다는 뜻이다.
- `sizeLimit: 8Gi`는 상한이다. 8Gi를 미리 잡아 두지 않고 실제로 쓴 만큼만 메모리를 차지한다. 상한을 넘으면 쓰기가 `No space left on device`로 실패한다.
- 여기에 쓴 데이터는 컨테이너의 메모리 사용량에 포함된다. `limits.memory: 80Gi`에 8Gi가 더해지는 것이 아니라, 80Gi 안에서 함께 쓴다.

#### cache: 쓰기 가능한 캐시 디렉터리 ####

- `medium`을 생략했기 때문에 노드 디스크(노드에 붙은 EBS 볼륨)에 만들어진다.
- 환경 변수 `XDG_CACHE_HOME=/home/vllm/.cache`와 `TRITON_CACHE_DIR=/home/vllm/.cache/triton`이 이 경로를 가리킨다. 그래서 다음 파일이 여기에 쌓인다.
  - S3에서 내려받은 모델 설정 파일(config, 토크나이저 등): `vllm/assets/model_streamer/` 아래
  - torch.compile 결과: `vllm/torch_compile_cache/` 아래
  - Triton이 컴파일한 GPU 커널: `triton/` 아래
- 모델 가중치는 runai_streamer가 S3에서 GPU 메모리로 바로 보내고 디스크에는 저장하지 않는다. 그래서 20Gi면 충분하다.
- emptyDir은 모든 사용자가 쓸 수 있는 권한으로 만들어진다. 그래서 컨테이너가 UID 2000으로 실행돼도 캐시를 쓸 곳이 확실히 있다.
- 사용량이 20Gi를 넘으면 kubelet이 파드를 축출(Evicted)한다.

#### 운영할 때 알아 둘 점 ####

- 새 파드는 빈 캐시로 시작하므로 torch.compile과 Triton 커널 컴파일을 처음부터 다시 한다. startupProbe에 최대 15분을 준 이유 중 하나다. 같은 파드 안에서 컨테이너만 재시작하면 캐시가 남아 있어서 더 빨리 뜬다.
- `cache`는 노드 디스크를 쓴다. GPU 노드의 EBS 볼륨(EC2NodeClass의 `blockDeviceMappings`)에 vLLM 이미지와 이 20Gi가 함께 들어갈 여유가 있어야 한다.


## 스케줄링 시간 측정 ##

### 1. 노드, 이미지, 컨테이너 타임라인 ###
```
NS=llm-serving
POD=$(kubectl get pod -n "$NS" -l app.kubernetes.io/name=gemma4-12b-vllm \
  -o jsonpath='{.items[0].metadata.name}')
NODE=$(kubectl get pod -n "$NS" "$POD" -o jsonpath='{.spec.nodeName}')
NODECLAIM=$(kubectl get nodeclaims -o json \
  | jq -r --arg n "$NODE" '.items[] | select(.status.nodeName == $n) | .metadata.name')
echo "pod=$POD node=$NODE nodeclaim=$NODECLAIM"

jq -rs '
def epoch: sub("\\.[0-9]+"; "") | fromdateiso8601;
def cond($o; $type): $o.status.conditions[]? | select(.type == $type) | .lastTransitionTime;
.[0] as $pod | .[1] as $nc | .[2] as $node | .[3] as $ev
| def event($reason): first($ev.items[]? | select(.reason == $reason) | .firstTimestamp // .eventTime);
[
  {k: "created",     step: "파드 생성",                                        t: $pod.metadata.creationTimestamp},
  {k: "nc_created",  step: "NodeClaim 생성 (Karpenter가 노드를 띄우기로 결정)", t: $nc.metadata.creationTimestamp},
  {k: "launched",    step: "EC2 인스턴스 생성 (NodeClaim Launched)",            t: cond($nc; "Launched")},
  {k: "registered",  step: "노드가 클러스터에 등록 (NodeClaim Registered)",      t: cond($nc; "Registered")},
  {k: "node_ready",  step: "kubelet 준비 완료 (Node Ready)",                    t: cond($node; "Ready")},
  {k: "initialized", step: "GPU 리소스 등록 완료 (NodeClaim Initialized)",       t: cond($nc; "Initialized")},
  {k: "scheduled",   step: "파드가 노드에 배정 (PodScheduled)",                  t: cond($pod; "PodScheduled")},
  {k: "pulling",     step: "이미지 받기 시작 (Pulling)",                         t: event("Pulling")},
  {k: "pulled",      step: "이미지 받기 완료 (Pulled)",                          t: event("Pulled")},
  {k: "started",     step: "컨테이너 시작",                                      t: $pod.status.containerStatuses[0].state.running.startedAt},
  {k: "ready",       step: "vLLM 준비 완료 (Pod Ready)",                         t: cond($pod; "Ready")}
]
| map(select(.t != null) | .e = (.t | epoch))
| sort_by(.e)
| (map({key: .k, value: .e}) | from_entries) as $e
| def dur($a; $b): if $e[$a] != null and $e[$b] != null then "\($e[$b] - $e[$a])초" else "-" end;
  (.[] | "\(.t)  +\(.e - $e.created)초  \(.step)"),
  "",
  "노드 준비 (파드 생성 → 노드 배정):  \(dur("created"; "scheduled"))",
  "이미지 받기 (Pulling → Pulled):     \(dur("pulling"; "pulled"))",
  "vLLM 기동 (컨테이너 시작 → Ready):  \(dur("started"; "ready"))",
  "전체 (파드 생성 → Ready):           \(dur("created"; "ready"))",
  "이미지 정보: \(first($ev.items[]? | select(.reason == "Pulled") | .message) // "-")"
' <(kubectl get pod -n "$NS" "$POD" -o json) \
  <(kubectl get nodeclaim "$NODECLAIM" -o json) \
  <(kubectl get node "$NODE" -o json) \
  <(kubectl get events -n "$NS" --field-selector involvedObject.name="$POD" -o json)
```

[결과]
```
pod=gemma4-12b-vllm-64bf5f5b7-mk94p node=ip-10-0-11-177.ap-northeast-2.compute.internal nodeclaim=gpu-qzshv
2026-11-23T15:36:08Z  +0초  파드 생성
2026-11-23T15:36:19Z  +11초  NodeClaim 생성 (Karpenter가 노드를 띄우기로 결정)
2026-11-23T15:36:21Z  +13초  EC2 인스턴스 생성 (NodeClaim Launched)
2026-11-23T15:36:43Z  +35초  노드가 클러스터에 등록 (NodeClaim Registered)
2026-11-23T15:36:53Z  +45초  kubelet 준비 완료 (Node Ready)
2026-11-23T15:37:13Z  +65초  GPU 리소스 등록 완료 (NodeClaim Initialized)
2026-11-23T15:37:13Z  +65초  파드가 노드에 배정 (PodScheduled)
2026-11-23T15:37:14Z  +66초  이미지 받기 시작 (Pulling)
2026-11-23T15:40:10Z  +242초  이미지 받기 완료 (Pulled)
2026-11-23T15:40:11Z  +243초  컨테이너 시작
2026-11-23T15:43:24Z  +436초  vLLM 준비 완료 (Pod Ready)

노드 준비 (파드 생성 → 노드 배정):  65초
이미지 받기 (Pulling → Pulled):     176초
vLLM 기동 (컨테이너 시작 → Ready):  193초
전체 (파드 생성 → Ready):           436초
이미지 정보: Successfully pulled image "vllm/vllm-openai:v0.33.0" in 2m56.371s (2m56.371s including waiting). Image size: 9738549569 bytes.
```

### 2. vLLM 기동 단계별 시간 ###
```
kubectl logs -n "$NS" "$POD" --timestamps \
  | grep -E "RunAI Streamer|Model loading took|torch.compile takes|Graph capturing finished|init engine|Application startup complete"
```

[결과]
```
2026-11-23T15:41:29.952313791Z (EngineCore pid=225) INFO 11-23 15:41:29 [model_runner.py:428] Model loading took 12.75 GiB memory and 12.762926 seconds
2026-11-23T15:43:08.549761612Z (EngineCore pid=225) INFO 11-23 15:43:08 [model_runner.py:1163] Graph capturing finished in 14 secs, took 0.52 GiB
2026-11-23T15:43:17.680269763Z (EngineCore pid=225) INFO 11-23 15:43:17 [model_runner.py:1163] Graph capturing finished in 7 secs, took 0.30 GiB
2026-11-23T15:43:18.971310602Z (EngineCore pid=225) INFO 11-23 15:43:18 [core.py:405] init engine (profile, create kv cache, warmup model) took 108.99 s (compilation: 54.72 s)
2026-11-23T15:43:22.393764308Z INFO:     Application startup complete.
```



## 참고자료 ##

* [vLLM Recipes, Google/gemma-4-12B-it (FP8 구성)](https://recipes.vllm.ai/Google/gemma-4-12B-it?variant=fp8&hardware=h100&features=reasoning)
* [RedHatAI/gemma-4-12B-it-FP8-Dynamic 모델 카드](https://huggingface.co/RedHatAI/gemma-4-12B-it-FP8-Dynamic)
* [AWS, Accelerate model loading on Amazon EKS](https://docs.aws.amazon.com/eks/latest/userguide/ml-inference-fast-model-loading.html)
* [vLLM, Using Docker, Run:ai Model Streamer](https://docs.vllm.ai/en/latest/models/extensions/runai_model_streamer/)
* [Gemma 4 12B 양자화 모델 카드의 Blackwell 메모](https://huggingface.co/aleksandard/gemma-4-12B-it-int4-MLPonly-AutoRound)
