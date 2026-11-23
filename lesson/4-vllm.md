
### 1. S3 모델 업로드 ###

```
# FP8 체크포인트를 받아 S3에 한 번 올립니다. 예비 버전이라 커밋을 고정하세요.
hf download RedHatAI/gemma-4-12B-it-FP8-Dynamic \
  --revision <COMMIT_SHA> \
  --local-dir ./gemma-4-12B-it-FP8-Dynamic

aws s3 sync ./gemma-4-12B-it-FP8-Dynamic \
  s3://<MODEL_BUCKET>/models/gemma-4-12B-it-FP8-Dynamic \
  --exclude ".cache/*"
```

### 2. IRSA 역할 ###
```
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::<MODEL_BUCKET>",
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
      "Resource": "arn:aws:s3:::<MODEL_BUCKET>/models/gemma-4-12B-it-FP8-Dynamic/*"
    }
  ]
}
```

### 3. vLLM 매니페스트 ###
```
apiVersion: v1
kind: Namespace
metadata:
  name: llm-serving
---
# S3 읽기 권한 (IRSA). EKS Pod Identity를 쓰면 annotation 대신 Pod Identity association을 만듭니다.
apiVersion: v1
kind: ServiceAccount
metadata:
  name: vllm-model-reader
  namespace: llm-serving
  annotations:
    eks.amazonaws.com/role-arn: arn:aws:iam::<ACCOUNT_ID>:role/<VLLM_S3_READ_ROLE>
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
  replicas: 2                       # KEDA로 스케일링하면 이 줄을 지우고 minReplicaCount: 2로 옮깁니다
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
        karpenter.sh/nodepool: gpu-text-g7e       # 실제 GPU NodePool 이름으로 변경
      tolerations:
        - key: nvidia.com/gpu
          operator: Exists
          effect: NoSchedule
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname     # 두 파드를 서로 다른 노드에 배치
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
        runAsUser: 2000                           # vLLM 이미지에 내장된 vllm 사용자
        runAsGroup: 0
        fsGroup: 0
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: vllm
          image: vllm/vllm-openai:v0.33.0          # 0.23.0 이상 필요. 운영에서는 @sha256 다이제스트로 고정
          command: ["vllm", "serve"]
          args:
            - s3://<MODEL_BUCKET>/models/gemma-4-12B-it-FP8-Dynamic
            - --load-format=runai_streamer         # S3에서 GPU 메모리로 바로 스트리밍
            - '--model-loader-extra-config={"concurrency":4}'
            - --served-model-name=gemma-4-12b
            - --kv-cache-dtype=fp8                 # KV 캐시도 8비트 (메모리 약 50% 절감)
            - --max-model-len=32768
            - --enable-prefix-caching
            - --reasoning-parser=gemma4
            - '--limit-mm-per-prompt={"image":4,"audio":0}'   # 오디오는 vllm[audio] 추가 설치가 필요해 끔
            - --host=0.0.0.0
            - --port=8000
          env:
            - name: AWS_REGION
              value: ap-northeast-2
            - name: AWS_DEFAULT_REGION
              value: ap-northeast-2
            - name: HF_HUB_OFFLINE                 # Hugging Face 접속 차단. 모든 파일을 S3에서 읽음
              value: "1"
            - name: RUNAI_STREAMER_CHUNK_BYTESIZE  # 4GiB 청크 (AWS 권장값)
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
            - name: http                           # OpenAI 호환 API와 /metrics 공용 포트
              containerPort: 8000
              protocol: TCP
          resources:                               # g7e.2xlarge(8 vCPU, 64GiB) 기준
            requests:
              cpu: "6"
              memory: 40Gi
              nvidia.com/gpu: "1"
            limits:
              memory: 40Gi
              nvidia.com/gpu: "1"
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop: ["ALL"]
          startupProbe:                            # S3 스트리밍 + torch.compile + CUDA graph 캡처 (최대 15분)
            httpGet:
              path: /health
              port: http
            periodSeconds: 10
            failureThreshold: 90
          readinessProbe:                          # Ready인 파드만 헤드리스 서비스 DNS에 나타남
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
            preStop:                               # DNS에서 빠질 시간을 준 뒤 종료
              exec:
                command: ["sleep", "20"]
          volumeMounts:
            - name: dshm
              mountPath: /dev/shm
            - name: cache
              mountPath: /home/vllm/.cache
      volumes:
        - name: dshm                               # PyTorch 프로세스 간 공유 메모리
          emptyDir:
            medium: Memory
            sizeLimit: 8Gi
        - name: cache                              # 설정 파일, torch.compile·Triton 캐시
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
  clusterIP: None                                  # 헤드리스: DNS가 파드 IP 목록을 그대로 반환
  publishNotReadyAddresses: false
  selector:
    app.kubernetes.io/name: gemma4-12b-vllm
  ports:
    - name: http
      port: 8000
      targetPort: http
      protocol: TCP
```


### 3. 설정 메모 ###

#### 모델과 이미지 ####
* 8비트 방식: Red Hat이 llm-compressor로 가중치와 활성값을 모두 FP8로 만든 체크포인트이다. Red Hat 평가에서 BF16 대비 성능을 약 100% 유지하였다. Google 원본(BF16)을 S3에 올리고 싶으면 S3 경로를 바꾸고 --quantization=fp8 한 줄을 추가하면 된다. 이 경우 vLLM이 로드할 때 FP8로 변환하고, S3에서 읽는 양은 약 2배(약 24GB)가 된다.
* vLLM 버전: 12B Unified는 vLLM 0.23.0 이상이 필요하다. CUDA 13 이미지는 노드 드라이버 R580 이상이 필요하다.

#### Run:ai Model Streamer ####
* concurrency 4: AWS 문서의 계산식 ceil(모델 크기 ÷ 청크 크기) 의 결과값이다. FP8 체크포인트를 약 13GB로 잡고 4GB 청크로 나눈 값입니다.
* CPU 메모리: 청크 4개를 동시에 읽으면 CPU 버퍼가 최대 약 16GB까지 커질 수 있으므로, 메모리를 40Gi로 설정하였다.
헤드리스 서비스와 스케일링

#### 선택 사항 ####
* 콜드 스타트 단축: 새 노드에서 파드가 뜰 때는 노드 기동, 수 GB짜리 이미지 pull, 가중치 스트리밍, torch.compile 순서로 시간이 듭니다. AWS 문서는 두 가지를 권장합니다 [3].
   * S3 Gateway VPC 엔드포인트를 두면 NAT 게이트웨이 병목이 없어진다.
   * torch.compile 캐시를 NVMe 인스턴스 스토어 hostPath에 두면, 같은 노드에서 재시작할 때 컴파일을 건너뛴다. 다만 Pod Security baseline 정책은 hostPath를 막아놓아서 위 YAML은 emptyDir을 사용하였다.
* PodDisruptionBudget: minAvailable: 1로 하나 추가해 두면, Karpenter가 노드를 정리할 때 두 파드가 동시에 내려가지 않는다.
문제가 생기면


## 참고자료 ##

* [vLLM Recipes, Google/gemma-4-12B-it (FP8 구성)](https://recipes.vllm.ai/Google/gemma-4-12B-it?variant=fp8&hardware=h100&features=reasoning)
* [RedHatAI/gemma-4-12B-it-FP8-Dynamic 모델 카드](https://huggingface.co/RedHatAI/gemma-4-12B-it-FP8-Dynamic)
* [AWS, Accelerate model loading on Amazon EKS](https://docs.aws.amazon.com/eks/latest/userguide/ml-inference-fast-model-loading.html)
* [vLLM, Using Docker, Run:ai Model Streamer](https://docs.vllm.ai/en/latest/models/extensions/runai_model_streamer/)
* [Gemma 4 12B 양자화 모델 카드의 Blackwell 메모](https://huggingface.co/aleksandard/gemma-4-12B-it-int4-MLPonly-AutoRound)
