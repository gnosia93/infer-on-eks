
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
