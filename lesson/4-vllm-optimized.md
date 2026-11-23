# SOCI 전용 Karpenter NodePool(gpu-soci)로 vLLM 스케줄링하기

## 개요

- 기존 `gpu` NodePool과 EC2NodeClass는 그대로 두고, SOCI 전용 EC2NodeClass와 NodePool을 `gpu-soci`라는 이름으로 새로 만듭니다.
- 기존 설정을 복사한 뒤 SOCI 관련 부분만 바꾸기 때문에 IAM 역할, 서브넷, 보안 그룹, taint, 라벨은 기존과 같습니다.
- 기존 노드는 drift로 교체되지 않습니다.
- Deployment는 nodeSelector로 `gpu-soci`를 고릅니다.

## 준비

- `kubectl`과 `jq`가 필요합니다.
- Deployment를 apply하는 셸에는 `BUCKET`(모델 버킷 이름)과 `AWS_REGION` 변수가 설정돼 있어야 합니다.
- 아래 명령은 실제 클러스터에서 검증하지 않았습니다. 단계마다 출력을 확인하면서 진행하세요.

## 1. 기존 설정 확인

```bash
SRC_NODECLASS=$(kubectl get nodepool gpu -o jsonpath='{.spec.template.spec.nodeClassRef.name}')
AMI_ALIAS=$(kubectl get ec2nodeclass "$SRC_NODECLASS" -o jsonpath='{.spec.amiSelectorTerms[0].alias}')
AMI_FAMILY=${AMI_ALIAS%%@*}
echo "기존 EC2NodeClass: $SRC_NODECLASS / AMI: $AMI_ALIAS / 계열: $AMI_FAMILY"
echo "--- 기존 userData ---"
kubectl get ec2nodeclass "$SRC_NODECLASS" -o jsonpath='{.spec.userData}'; echo
```

- **계열**: `al2023`이나 `bottlerocket`이 나와야 합니다. 비어 있으면 alias 대신 AMI ID를 직접 지정한 경우라 아래 스크립트를 그대로 쓸 수 없습니다.
- **기존 userData**: 내용이 있으면 새 클래스에서는 SOCI 설정으로 대체되어 빠집니다. 꼭 필요한 내용이면 2단계의 `USERDATA`에 합쳐 넣으세요.

## 2. EC2NodeClass `gpu-soci` 만들기

먼저 AMI 계열에 맞는 SOCI 설정을 변수에 담습니다. 둘 중 하나만 실행하세요. 설정 값은 Karpenter Blueprints의 SOCI 예제를 기준으로 했습니다.

### AL2023인 경우

```bash
USERDATA=$(cat <<'EOF'
apiVersion: node.eks.aws/v1alpha1
kind: NodeConfig
spec:
  featureGates:
    FastImagePull: true
EOF
)
BDM='[{"deviceName":"/dev/xvda","ebs":{"volumeSize":"100Gi","volumeType":"gp3","iops":3000,"throughput":600,"encrypted":true}}]'
```

### Bottlerocket인 경우

```bash
USERDATA=$(cat <<'EOF'
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
)
BDM='[{"deviceName":"/dev/xvda","ebs":{"volumeSize":"4Gi","volumeType":"gp3","encrypted":true}},{"deviceName":"/dev/xvdb","ebs":{"volumeSize":"100Gi","volumeType":"gp3","iops":3000,"throughput":600,"encrypted":true}}]'
```

### 클래스 만들기

기존 클래스를 복사해서 `gpu-soci`를 만듭니다. 바뀌는 항목은 AMI(`@latest`), 블록 디바이스, userData뿐입니다.

```bash
kubectl get ec2nodeclass "$SRC_NODECLASS" -o json \
  | jq --arg alias "${AMI_FAMILY:?}@latest" --arg ud "${USERDATA:?}" --argjson bdm "${BDM:?}" '{
      apiVersion: .apiVersion,
      kind: .kind,
      metadata: {name: "gpu-soci"},
      spec: (.spec
        | .amiSelectorTerms = [{alias: $alias}]
        | .blockDeviceMappings = $bdm
        | .userData = $ud)
    }' \
  | kubectl apply -f -

kubectl get ec2nodeclass gpu-soci
```

`READY`가 `True`가 되면 다음 단계로 넘어갑니다. AMI를 `@latest`로 둔 이유는 SOCI가 요구하는 AMI 버전(AL2023 v20250821 이후, Bottlerocket v1.44.0 이후)을 확실히 맞추기 위해서입니다.

## 3. NodePool `gpu-soci` 만들기

기존 `gpu` NodePool을 복사합니다. 그래서 taint, 라벨, disruption 설정은 그대로 따라옵니다. 바꾸는 항목은 다음과 같습니다.

- EC2NodeClass를 `gpu-soci`로 연결합니다.
- 인스턴스를 고르는 조건(`instance-type`, `karpenter.k8s.aws/instance-*`)을 지우고 g6e.4xlarge 하나로 고정합니다.
- GPU 상한을 2개로 정합니다. 레플리카 1개에 롤링 업데이트 중 1개가 더 필요하기 때문입니다.

```bash
kubectl get nodepool gpu -o json \
  | jq '{
      apiVersion: .apiVersion,
      kind: .kind,
      metadata: {name: "gpu-soci"},
      spec: (.spec
        | .template.spec.nodeClassRef.name = "gpu-soci"
        | .template.spec.requirements |= (
            map(select(.key | test("^(node\\.kubernetes\\.io/instance-type|karpenter\\.k8s\\.aws/instance-.+)$") | not))
            + [{key: "node.kubernetes.io/instance-type", operator: "In", values: ["g6e.4xlarge"]}])
        | .limits = {"nvidia.com/gpu": "2"})
    }' \
  | kubectl apply -f -

kubectl get nodepool gpu-soci
```

레플리카를 늘릴 때는 `limits`도 함께 올리세요.

## 4. NVIDIA device plugin이 새 노드에 뜨는지 확인

AL2023 노드는 NVIDIA device plugin DaemonSet이 있어야 `nvidia.com/gpu` 리소스가 생깁니다. Bottlerocket은 OS에 device plugin이 들어 있어서 이 단계를 건너뛰어도 됩니다.

```bash
kubectl get ds -A | grep -i nvidia
kubectl get ds -n <네임스페이스> <DaemonSet 이름> \
  -o jsonpath='{.spec.template.spec.nodeSelector}{"\n"}{.spec.template.spec.affinity}{"\n"}{.spec.template.spec.tolerations}{"\n"}'
```

nodeSelector나 affinity가 `karpenter.sh/nodepool: gpu`처럼 기존 NodePool에만 맞는 조건이면, 새 노드에는 device plugin이 뜨지 않습니다. 그러면 vLLM 파드가 계속 Pending으로 남습니다. 이 경우에는 조건에 `gpu-soci`를 추가하세요.

## 5. Deployment를 `gpu-soci`로 스케줄링

Deployment는 AWS DLC vLLM 이미지를 쓰고, nodeSelector로 `gpu-soci` NodePool을 고릅니다. `BUCKET`과 `AWS_REGION` 변수가 설정된 셸에서 실행하세요.

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
        karpenter.sh/nodepool: gpu-soci             # SOCI parallel pull이 켜진 전용 NodePool
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

## 6. 확인

```bash
# gpu-soci 노드가 생기는지 확인
kubectl get nodeclaims -l karpenter.sh/nodepool=gpu-soci

# 새 노드에 GPU 리소스가 잡혔는지 확인 (1이 나와야 함)
kubectl get nodes -l karpenter.sh/nodepool=gpu-soci \
  -o custom-columns='NAME:.metadata.name,GPU:.status.allocatable.nvidia\.com/gpu'

# 이미지 pull 시간 확인
kubectl get events -n llm-serving --field-selector reason=Pulled \
  -o custom-columns=TIME:.firstTimestamp,MESSAGE:.message
```

새 파드가 Ready가 되면 기존 파드가 내려갑니다. 그 뒤 비게 된 `gpu` 노드는 `gpu` NodePool의 consolidation 설정에 따라 정리됩니다.

## 참고

- **되돌리기**: nodeSelector를 다시 `gpu`로 바꿔 apply하면 됩니다. 전용 풀을 없애려면 `kubectl delete nodepool gpu-soci`와 `kubectl delete ec2nodeclass gpu-soci`를 실행합니다. NodePool을 지우면 그 풀의 노드도 함께 종료됩니다.
- **AMI 고정**: AMI가 `@latest`라서 새 AMI가 나오면 Karpenter가 drift로 `gpu-soci` 노드를 교체하고, 그때 vLLM이 재시작됩니다. 운영 환경에서는 검증한 버전으로 alias를 고정하세요(`al2023@vYYYYMMDD` 형식).

## 참고 자료

- [Karpenter Blueprints: Using SOCI snapshotter parallel pull/unpack mode](https://aws-samples.github.io/karpenter-blueprints/blueprints/soci-snapshotter/)
- [nodeadm 예제: Enabling fast image pull](https://awslabs.github.io/amazon-eks-ami/nodeadm/doc/examples/)
- [AWS DLC: Available Images](https://aws.github.io/deep-learning-containers/reference/available_images/)
- [AWS DLC: Region Availability](https://aws.github.io/deep-learning-containers/reference/region_availability/)

