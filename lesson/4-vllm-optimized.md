## vLLM Deployment를 AWS DLC 이미지로 바꾸고 SOCI parallel pull 적용하기 ##

두 설정은 바꾸는 곳이 다릅니다.

- 이미지는 Deployment에서 바꿉니다.
- SOCI parallel pull은 노드의 containerd 설정이라 NodePool `gpu`가 쓰는 Karpenter EC2NodeClass에서 켭니다.

EC2NodeClass를 먼저 바꾸고 Deployment를 apply하면, 새 파드가 SOCI가 켜진 새 노드에서 DLC 이미지를 받습니다.

## 1. 적용 전 확인

### NVIDIA 드라이버 버전

[DLC vLLM 이미지](https://aws.github.io/deep-learning-containers/vllm/)는 CUDA 13.0 기반이라 NVIDIA 드라이버 580 이상을 기준으로 합니다. 지금 노드의 드라이버 버전을 확인합니다.

```bash
kubectl exec -n llm-serving deploy/gemma4-12b-vllm -- \
  nvidia-smi --query-gpu=driver_version --format=csv,noheader
```

580 미만이면 EC2NodeClass의 AMI를 최신으로 올리는 게 안전합니다. 이미지에 CUDA 호환 패키지(`cuda-compat-13-0`)가 들어 있긴 합니다.

### EC2NodeClass 현재 설정

NodePool `gpu`가 쓰는 EC2NodeClass와 현재 설정을 봅니다.

```bash
NODECLASS=$(kubectl get nodepool gpu -o jsonpath='{.spec.template.spec.nodeClassRef.name}')
echo "EC2NodeClass: $NODECLASS"
kubectl get ec2nodeclass "$NODECLASS" \
  -o jsonpath='{.spec.amiSelectorTerms}{"\n"}{.spec.userData}{"\n"}{.spec.blockDeviceMappings}{"\n"}'
kubectl get nodepools -o custom-columns=NODEPOOL:.metadata.name,NODECLASS:.spec.template.spec.nodeClassRef.name
```

- **AMI 종류**: `amiSelectorTerms`의 alias가 `al2023@...`이면 AL2023, `bottlerocket@...`이면 Bottlerocket입니다. 2단계에서 해당하는 patch를 고릅니다.
- **userData**: 비어 있어야 아래 patch를 그대로 쓸 수 있습니다. 이미 내용이 있으면 patch가 덮어쓰므로, 기존 내용과 합쳐서 넣어야 합니다.
- **공유 여부**: 같은 EC2NodeClass를 다른 NodePool도 쓰고 있다면 그 노드들에도 똑같이 적용됩니다.

### 2. EC2NodeClass에서 SOCI parallel pull 켜기 ###

SOCI parallel pull은 이미지 레이어를 여러 연결로 나눠 동시에 받고 동시에 풀어서 pull 시간을 줄입니다. 받은 레이어를 디스크에 버퍼링하기 때문에 EBS 처리량도 함께 올립니다. 아래 설정은 [Karpenter Blueprints의 SOCI 예제](https://aws-samples.github.io/karpenter-blueprints/blueprints/soci-snapshotter/)를 기준으로 했습니다.

#### AL2023 ####

AMI가 v20250821 이후 버전이어야 합니다. [nodeadm 문서](https://awslabs.github.io/amazon-eks-ami/nodeadm/doc/examples/)에 따르면 `FastImagePull`은 실험 기능이고, 2xlarge보다 작은 인스턴스에서는 무시됩니다. 기본값이 ECR에 맞춰져 있어서 따로 튜닝할 필요는 없습니다(이미지당 동시 다운로드 20, 동시 언팩 12, 청크 16MB).

```bash
kubectl patch ec2nodeclass "$NODECLASS" --type merge -p "$(cat <<'EOF'
spec:
  blockDeviceMappings:
    - deviceName: /dev/xvda
      ebs:
        volumeSize: 100Gi
        volumeType: gp3
        iops: 3000
        throughput: 600
        encrypted: true
  userData: |
    apiVersion: node.eks.aws/v1alpha1
    kind: NodeConfig
    spec:
      featureGates:
        FastImagePull: true
EOF
)"
```

#### Bottlerocket ####

v1.44.0 이후 버전이어야 합니다. 기본값이 보수적이라 값을 직접 지정합니다. `/dev/xvdb`가 이미지를 저장하는 데이터 볼륨입니다.

```bash
kubectl patch ec2nodeclass "$NODECLASS" --type merge -p "$(cat <<'EOF'
spec:
  blockDeviceMappings:
    - deviceName: /dev/xvda
      ebs:
        volumeSize: 4Gi
        volumeType: gp3
        encrypted: true
    - deviceName: /dev/xvdb
      ebs:
        volumeSize: 100Gi
        volumeType: gp3
        iops: 3000
        throughput: 600
        encrypted: true
  userData: |
    [settings.container-runtime]
    snapshotter = "soci"

    [settings.container-runtime-plugins.soci-snapshotter]
    pull-mode = "parallel-pull-unpack"

    [settings.container-runtime-plugins.soci-snapshotter.parallel-pull-unpack]
    max-concurrent-downloads-per-image = 20
    concurrent-download-chunk-size = "16mb"
    max-concurrent-unpacks-per-image = 12
    discard-unpacked-layers = true
EOF
)"
```

#### 설정할 때 알아 둘 점 ####

- **EBS 처리량**: 600MiB/s, 3000 IOPS는 nodeadm 문서가 권장하는 최소 시작점입니다. gp3 최대치인 1000MiB/s, 16000 IOPS까지 올리면 더 빨라질 수 있지만 비용이 늘어납니다.
- **NVMe 대안**: g6e.4xlarge에는 600GB 로컬 NVMe가 있습니다. EBS 처리량을 올리는 대신 `instanceStorePolicy: RAID0`로 containerd와 SOCI 데이터를 NVMe에 둘 수도 있습니다.
- **노드 교체 주의**: EC2NodeClass를 바꾸면 Karpenter가 기존 노드를 drift로 판단해 새 노드로 교체합니다. 레플리카가 1개라 교체 중에 vLLM이 잠깐 멈출 수 있습니다.

#### 3. Deployment: DLC 이미지로 변경 ####

Service는 바뀌지 않으니 Deployment만 apply합니다. `BUCKET`(모델 버킷 이름)과 `AWS_REGION` 변수가 설정된 셸에서 실행합니다.

```bash
kubectl apply -f - <<EOF
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
      serviceAccountName: vllm-model-reader         # eksctl이 만든 IRSA 서비스 어카운트
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
        runAsUser: 2000                             # DLC 이미지에는 비root 사용자가 없어 임의 UID로 실행
        runAsGroup: 0
        fsGroup: 0
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: vllm
          image: 763104351884.dkr.ecr.${AWS_REGION:?}.amazonaws.com/vllm:server-cuda-v2.8   # AWS DLC vLLM 0.33.0 (AL2023). 운영에서는 @sha256 다이제스트로 고정
          command: ["vllm", "serve"]                # DLC ENTRYPOINT도 결국 vllm serve를 실행
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
              value: ${AWS_REGION}
            - name: AWS_DEFAULT_REGION
              value: ${AWS_REGION}
            - name: HOME                            # passwd에 없는 UID라 HOME을 쓰기 가능한 emptyDir로 지정
              value: /home/vllm
            - name: USER                            # getpass.getuser()가 passwd 조회 없이 사용자 이름을 얻도록
              value: vllm
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
              mountPath: /home/vllm                 # HOME 전체를 emptyDir로
      volumes:
        - name: dshm                                # PyTorch 프로세스 간 공유 메모리
          emptyDir:
            medium: Memory
            sizeLimit: 8Gi
        - name: cache                               # HOME. 설정 파일, torch.compile·Triton 캐시
          emptyDir:
            sizeLimit: 20Gi
EOF
```

#### 바꾼 내용 ####

- **이미지**: 같은 리전의 private ECR에 있는 DLC vLLM `server-cuda-v2.8`로 바꿨습니다. vLLM 버전이 기존과 같은 0.33.0이라 args는 그대로 둡니다([Available Images](https://aws.github.io/deep-learning-containers/reference/available_images/)). S3 스트리밍에 필요한 runai-model-streamer도 이미지에 들어 있습니다. `763104351884`는 서울 리전의 DLC 계정이고, 일부 리전은 계정이 다릅니다([Region Availability](https://aws.github.io/deep-learning-containers/reference/region_availability/)). 같은 리전의 ECR에서 받으면 SOCI가 쓰는 HTTP range 요청도 지원됩니다.
- **command**: DLC의 [ENTRYPOINT 스크립트](https://github.com/aws/deep-learning-containers/blob/main/scripts/docker/vllm/dockerd_entrypoint.sh)는 텔레메트리 스크립트를 실행한 뒤 `vllm serve "$@"`를 실행합니다. 그래서 `command`를 그대로 두면 텔레메트리만 빠지고 동작은 같습니다.
- **비root 실행**: DLC [Dockerfile](https://github.com/aws/deep-learning-containers/blob/main/docker/vllm/Dockerfile.amzn2023)에는 `USER` 지정이 없어서 기본적으로 root로 실행됩니다. UID 2000은 유지했습니다. 대신 이 UID가 이미지의 사용자 목록에 없으므로 `HOME`과 `USER`를 지정했고, `cache` emptyDir을 `/home/vllm` 전체에 마운트해 쓰기 가능한 홈 디렉터리를 만들었습니다. 그래도 권한 에러가 나면 `runAsNonRoot`와 `runAsUser`를 지워 DLC 기본값처럼 root로 실행합니다.

#### 4. 순서와 확인 ####

1. 2단계의 EC2NodeClass patch를 실행합니다.
2. 3단계의 Deployment를 apply합니다. 새 파드를 위해 Karpenter가 SOCI가 켜진 g6e.4xlarge를 새로 띄웁니다.
3. 새 파드의 이미지 pull 시간을 확인합니다.

```bash
kubectl get events -n llm-serving --field-selector reason=Pulled \
  -o custom-columns=TIME:.firstTimestamp,MESSAGE:.message
```

참고로 Karpenter Blueprints의 측정에서는 9.3GB짜리 DLC vLLM 이미지의 pull 시간이 기본 설정에서 2분 10초였습니다. SOCI parallel pull을 켜면 AL2023에서 약 40초, Bottlerocket에서 약 23초로 줄었습니다. 이 측정은 네트워크와 EBS 대역폭이 8Gbps를 넘는 인스턴스에서 했습니다.

## 참고 자료

- [AWS DLC: LLM Serving using vLLM DLC](https://aws.github.io/deep-learning-containers/vllm/)
- [AWS DLC: Available Images](https://aws.github.io/deep-learning-containers/reference/available_images/)
- [AWS DLC: Region Availability](https://aws.github.io/deep-learning-containers/reference/region_availability/)
- [DLC vLLM Dockerfile (Amazon Linux 2023)](https://github.com/aws/deep-learning-containers/blob/main/docker/vllm/Dockerfile.amzn2023)
- [DLC vLLM ENTRYPOINT 스크립트](https://github.com/aws/deep-learning-containers/blob/main/scripts/docker/vllm/dockerd_entrypoint.sh)
- [Karpenter Blueprints: Using SOCI snapshotter parallel pull/unpack mode](https://aws-samples.github.io/karpenter-blueprints/blueprints/soci-snapshotter/)
- [nodeadm 예제: Enabling fast image pull](https://awslabs.github.io/amazon-eks-ami/nodeadm/doc/examples/)


