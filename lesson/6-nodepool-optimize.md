## GPU 노드풀 최적화: Bottlerocket + SOCI Parallel Pull ##

기존 `gpu` NodePool과 EC2NodeClass는 그대로 둔다. Bottlerocket AMI에 SOCI parallel pull을 켠 `gpu-optimized` NodePool과 EC2NodeClass를 따로 만든다. vLLM Deployment는 nodeSelector만 바꿔 새 풀로 옮긴다. 4장에서 잰 콜드 스타트는 약 436초였고, 그중 이미지 받기가 약 176초였다. 이 장의 목표는 이미지 받는 시간을 줄이는 것이다.

### 구성 ###
| 항목 | gpu (기존) | gpu-optimized (이 장) |
|---|---|---|
| AMI | AL2023 NVIDIA (`al2023@latest`) | Bottlerocket NVIDIA 변형 `aws-k8s-1.34-nvidia` (버전 고정) |
| 이미지 받기 | containerd 기본 방식 | SOCI snapshotter의 parallel pull 모드 |
| 디스크 | 루트 EBS 600Gi gp3 | 컨테이너 데이터는 NVMe 인스턴스 스토어(g6e.4xlarge는 600GB). EBS는 OS 4Gi + 데이터 20Gi |
| GPU 디바이스 플러그인 | `nvidia` 네임스페이스의 nvdp DaemonSet | OS에 들어 있는 `nvidia-k8s-device-plugin` 서비스 |
| taint | `nvidia.com/gpu=present:NoSchedule` | `nvidia.com/gpu=bottlerocket:NoSchedule` |
| 노드 접속 | `kubectl debug node` + `chroot /host` | SSM 세션 (control/admin 컨테이너) |

SOCI parallel pull은 다음처럼 동작한다.
- **레이어 내려받기:** 레이어를 정해진 크기(이 장에서는 16MB)로 나눈다. 나눈 조각을 HTTP range GET 여러 개로 동시에 받는다. 받은 데이터는 메모리가 아니라 디스크의 임시 파일에 쓴다.
- **레이어 풀기:** containerd 기본 방식은 레이어를 하나씩 차례로 푼다. parallel pull 모드는 여러 레이어를 동시에 푼다.
- **이미지 준비:** lazy loading과 달리 SOCI 인덱스가 필요 없다. 이미지를 모두 받아 푼 뒤에 컨테이너를 시작한다. 그래서 이미지를 다시 만들 필요가 없다.

AWS 블로그는 약 10GB짜리 vLLM DLC 이미지를 m6i.8xlarge에서 받아 비교했다. 받는 시간이 1분 53초에서 45초로 줄었다.

### 사전 준비 ###
| 항목 | 조건 |
|---|---|
| Karpenter | 1.8.1. 3장의 `gpu` NodePool과 EC2NodeClass |
| 노드 IAM 역할 | `eksctl-KarpenterNodeRole-${CLUSTER_NAME}`. eksctl이 `AmazonSSMManagedInstanceCore`를 붙여 두므로 SSM으로 노드에 들어갈 수 있다. |
| NVIDIA device plugin | 3장의 `nvdp` 릴리스 (차트 0.20.2, `gfd.enabled=true`) |
| vLLM | 4장의 `gemma4-12b-vllm` Deployment. 매니페스트를 apply 하는 셸에 `BUCKET`, `AWS_REGION`이 설정돼 있어야 한다. |
| 도구 | aws, kubectl, helm, jq. SSM 세션으로 노드에 들어가려면 Session Manager 플러그인도 필요하다. |

### 환경 설정 ###
```
export AWS_REGION=$(aws ec2 describe-availability-zones --query 'AvailabilityZones[0].RegionName' --output text)
export CLUSTER_NAME="infer-on-eks"
export K8S_VERSION="1.34"
export BOTTLEROCKET_VERSION=$(aws ssm get-parameter \
  --name "/aws/service/bottlerocket/aws-k8s-${K8S_VERSION}-nvidia/x86_64/latest/image_version" \
  --query Parameter.Value --output text | cut -d- -f1)
echo "Region: ${AWS_REGION}"
echo "Cluster Name: ${CLUSTER_NAME}"
echo "EKS Version: ${K8S_VERSION}"
echo "Bottlerocket Version: ${BOTTLEROCKET_VERSION}"
```
- **BOTTLEROCKET_VERSION:** 이 리전에 나온 최신 Bottlerocket NVIDIA 변형의 버전이다. 값에 빌드 ID가 붙어 있으면(`1.70.0-xxxxxxxx`) 잘라 낸다. SOCI parallel pull은 1.44.0 이상에서 쓸 수 있다. SOCI 디렉터리까지 NVMe로 옮기려면 1.46.0 이상이어야 한다(2.2절).

[예상 결과]
```
Region: ap-northeast-2
Cluster Name: infer-on-eks
EKS Version: 1.34
Bottlerocket Version: 1.70.0
```

### 1. nvdp DaemonSet이 새 노드에 뜨지 않게 하기 ###
Bottlerocket NVIDIA 변형에는 NVIDIA device plugin이 OS 서비스(`nvidia-k8s-device-plugin`)로 들어 있다. 이 서비스가 GPU를 `nvidia.com/gpu`로 kubelet에 등록한다. 그래서 3장에서 설치한 nvdp DaemonSet은 이 노드에 필요 없다. 둘 다 뜨면 한 노드에서 플러그인 두 개가 같은 리소스를 등록하려고 한다. 그래서 nvdp가 뜨지 않게 한다.

nvdp는 다음 순서로 노드에 뜬다.
1. nvdp 차트에 포함된 NFD(Node Feature Discovery) worker가 노드에 뜬다. 차트 기본값에서 NFD worker는 `nvidia.com/gpu` taint 가운데 값이 `present`인 것만 허용한다(`operator: Equal`).
2. NFD worker가 노드에 `feature.node.kubernetes.io/pci-10de.present=true` 레이블을 붙인다. `10de`는 NVIDIA의 PCI 벤더 ID다.
3. nvdp와 GFD DaemonSet은 affinity로 이 레이블이 있는 노드를 고른다.

그래서 새 풀의 taint 값을 `bottlerocket`으로 둔다. 그러면 NFD worker가 뜨지 않아 레이블이 붙지 않고, nvdp와 GFD도 뜨지 않는다. 3장 NodePool 주석에는 "present 와 다른값을 설정하면 nvidia-device-plugin 이 동작하지 않는다"고 적혀 있다. 이번에는 그 동작을 일부러 이용한다. vLLM 파드의 toleration은 `operator: Exists`라서 값과 상관없이 이 taint를 허용한다.

설치된 nvdp 릴리스가 차트 기본값을 그대로 쓰는지 확인한다.
```
helm get values nvdp -n nvidia --all -o json | jq '.nfd.worker.tolerations'
```

[예상 결과]
```
[
  {
    "effect": "NoSchedule",
    "key": "node-role.kubernetes.io/master",
    "operator": "Equal",
    "value": ""
  },
  {
    "effect": "NoSchedule",
    "key": "nvidia.com/gpu",
    "operator": "Equal",
    "value": "present"
  }
]
```
`nvidia.com/gpu` 항목이 `operator: Exists`라면 이 방법은 통하지 않는다. 그때는 nvdp 차트 `affinity`의 세 조건에 `karpenter.sh/nodepool NotIn [gpu-optimized]`를 각각 더한다.

### 2. EC2NodeClass와 NodePool 만들기 ###

#### 2.1 매니페스트 ####
```
cat <<EOF > nodepool-gpu-optimized.yaml
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: gpu-optimized
spec:
  template:
    metadata:
      labels:
        nodeType: "nvidia"
    spec:
      requirements:
        - key: kubernetes.io/arch
          operator: In
          values: ["amd64"]
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["spot", "on-demand", "reserved"]
        - key: karpenter.k8s.aws/instance-category
          operator: In
          values: ["g", "p"]
        - key: karpenter.k8s.aws/instance-local-nvme
          operator: Gt
          values: ["99"]                 # NVMe 인스턴스 스토어가 100GiB 이상인 인스턴스만 고른다
      nodeClassRef:
        group: karpenter.k8s.aws
        kind: EC2NodeClass
        name: gpu-optimized
      expireAfter: 720h # 30 * 24h = 720h
      taints:
      - key: "nvidia.com/gpu"
        value: "bottlerocket"            # present가 아니므로 NFD worker가 뜨지 않고, 그래서 nvdp DaemonSet도 뜨지 않는다 (1절)
        effect: NoSchedule               # GPU는 Bottlerocket에 들어 있는 device plugin이 등록한다
  limits:
    cpu: 1000
  disruption:
    consolidationPolicy: WhenEmpty
    consolidateAfter: 20m
---
apiVersion: karpenter.k8s.aws/v1
kind: EC2NodeClass
metadata:
  name: gpu-optimized
spec:
  role: "eksctl-KarpenterNodeRole-${CLUSTER_NAME:?}"
  amiSelectorTerms:
    # GPU 인스턴스에는 Karpenter가 NVIDIA 변형(aws-k8s-${K8S_VERSION}-nvidia)을 고른다
    - alias: bottlerocket@v${BOTTLEROCKET_VERSION:?}
  subnetSelectorTerms:
    - tags:
        karpenter.sh/discovery: "${CLUSTER_NAME}"
  securityGroupSelectorTerms:
    - tags:
        karpenter.sh/discovery: "${CLUSTER_NAME}"
  instanceStorePolicy: RAID0             # NVMe를 포맷해 컨테이너 데이터와 SOCI 디렉터리를 옮긴다 (2.2절)
  blockDeviceMappings:
    - deviceName: /dev/xvda              # OS 볼륨
      ebs:
        volumeSize: 4Gi
        volumeType: gp3
        encrypted: true
    - deviceName: /dev/xvdb              # 데이터 볼륨: NVMe로 옮기지 않은 나머지 데이터
      ebs:
        volumeSize: 20Gi
        volumeType: gp3
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
kubectl apply -f nodepool-gpu-optimized.yaml
```
NodePool은 `nodeClassRef`, taint 값, NVMe 조건만 다르다. requirements의 나머지, 레이블, expireAfter, limits, disruption은 `gpu` 풀과 같다. NVMe 조건이 없으면 NVMe가 없는 인스턴스(예: p3.2xlarge)가 뜰 수 있다. 그런 노드에서는 컨테이너 데이터가 20Gi 데이터 볼륨에 쌓이므로 vLLM 이미지가 들어가지 않는다.

#### 2.2 EC2NodeClass 설정 ####
| 항목 | 설명 |
|---|---|
| `amiSelectorTerms` | `bottlerocket@v1.70.0`처럼 버전을 고정한다. Karpenter는 이 버전의 일반 변형과 NVIDIA 변형을 함께 찾고, GPU 인스턴스에는 NVIDIA 변형을 쓴다. `@latest`로 두면 새 버전이 나올 때마다 drift로 노드가 교체되고 vLLM도 다시 뜬다. 최근 Bottlerocket 릴리스 간격은 1~2주다. |
| `instanceStorePolicy` | `RAID0`이면 Karpenter가 userData에 부팅 명령 `000-mount-instance-storage`를 넣는다. 이 명령은 먼저 `apiclient ephemeral-storage init`으로 NVMe 디스크를 묶어 xfs로 포맷한다. 디스크가 하나면 RAID 없이 그대로 쓴다. 이어서 `apiclient ephemeral-storage bind`로 기본 디렉터리를 NVMe로 옮긴다. 기본 디렉터리는 `/var/lib/containerd`, `/var/lib/kubelet`, `/var/log/pods`, `/var/lib/soci-snapshotter`, `/var/lib/host-containerd`다. SOCI는 받은 레이어를 디스크에 쓰므로 디스크가 받는 시간을 좌우한다. |
| Bottlerocket 버전 조건 | Karpenter는 Bottlerocket 1.46.0 이상에서만 위의 기본 목록으로 옮긴다. 버전이 그보다 낮으면 containerd, kubelet, 파드 로그 디렉터리만 옮기고 SOCI 데이터는 EBS에 남긴다. Karpenter는 노드의 ephemeral-storage도 NVMe 크기로 계산한다. |
| `/dev/xvda` | Bottlerocket OS 볼륨이다. OS 이미지가 4GiB라서 Karpenter 기본값과 같은 4Gi로 둔다. |
| `/dev/xvdb` | 데이터 볼륨이다. 컨테이너 데이터가 NVMe로 가므로 Karpenter 기본값과 같은 20Gi, 기본 성능(3,000 IOPS, 125MiB/s)으로 둔다. NVMe로 옮기지 않은 나머지 데이터가 여기에 남는다. |
| `encrypted` | 블록 디바이스를 직접 적으면 Karpenter 기본 매핑을 통째로 대신한다. 그래서 EBS 암호화를 명시한다. 인스턴스 스토어는 하드웨어에서 암호화된다. |
| `userData` | Bottlerocket 설정 API의 TOML이다. Karpenter가 클러스터 이름, API 서버 주소, 레이블, taint, 위의 부팅 명령을 덧붙인다. Karpenter는 `settings.kubernetes` 아래의 모르는 키만 버린다. `container-runtime` 같은 다른 설정은 그대로 넘긴다. |

#### 2.3 SOCI 설정 ####
값은 Karpenter Blueprint 예제와 같다.

| 설정 | Bottlerocket 기본값 | 이 장의 값 | 설명 |
|---|---|---|---|
| `container-runtime.snapshotter` | `overlayfs` | `soci` | SOCI가 이미지를 받고 스냅샷을 만든다. 부팅할 때만 적용된다. |
| `pull-mode` | `parallel-pull-unpack` | `parallel-pull-unpack` | 이미지를 모두 받은 뒤 시작하는 방식이다. 현재는 이 값만 쓸 수 있다. |
| `max-concurrent-downloads-per-image` | 3 | 20 | 이미지 하나를 받을 때 동시에 여는 연결 수다. ECR 권장값은 10~20이다. |
| `concurrent-download-chunk-size` | `unlimited` | `16mb` | 레이어를 나누는 크기다. `unlimited`면 레이어 하나를 연결 하나로 받는다. ECR 권장값은 16mb다. |
| `max-concurrent-unpacks-per-image` | 1 | 12 | 동시에 푸는 레이어 수다. 이미지에 있는 큰 레이어(1GB 이상) 수에 맞춘다. AWS 블로그는 AI/ML 이미지에 10 안팎을 권한다. |
| `discard-unpacked-layers` | `false` | `true` | 레이어를 푼 뒤 압축 레이어를 지워 디스크를 아낀다. 노드에서 이미지를 push하지 않으므로 안전하다. |

#### 2.4 적용 확인 ####
```
kubectl get ec2nodeclass,nodepool
kubectl get ec2nodeclass gpu-optimized \
  -o jsonpath='{range .status.amis[*]}{.name}{"\t"}{.id}{"\n"}{end}'
```

[예상 결과]
```
NAME                                           READY   AGE
ec2nodeclass.karpenter.k8s.aws/gpu             True    30d
ec2nodeclass.karpenter.k8s.aws/gpu-optimized   True    15s
NAME                                  NODECLASS       NODES   READY   AGE
nodepool.karpenter.sh/gpu             gpu             1       True    30d
nodepool.karpenter.sh/gpu-optimized   gpu-optimized   0       True    15s
bottlerocket-aws-k8s-1.34-nvidia-x86_64-v1.70.0-xxxxxxxx    ami-0xxxxxxxxxxxxxxxx
bottlerocket-aws-k8s-1.34-nvidia-aarch64-v1.70.0-xxxxxxxx   ami-0xxxxxxxxxxxxxxxx
bottlerocket-aws-k8s-1.34-x86_64-v1.70.0-xxxxxxxx           ami-0xxxxxxxxxxxxxxxx
bottlerocket-aws-k8s-1.34-aarch64-v1.70.0-xxxxxxxx          ami-0xxxxxxxxxxxxxxxx
```
NodePool이 amd64만 허용하므로 GPU 노드에는 `nvidia-x86_64` AMI가 쓰인다.

### 3. 새 노드 확인 ###
vLLM을 옮기기 전에 테스트 파드로 노드를 하나 띄운다. 이 노드에서 GPU, device plugin, NVMe, SOCI 설정을 먼저 확인한다.

#### 3.1 GPU 테스트 파드 ####
```
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: gpu-pod-br
spec:
  restartPolicy: Never
  nodeSelector:
    karpenter.sh/nodepool: gpu-optimized
    node.kubernetes.io/instance-type: g6e.4xlarge
  containers:
    - name: cuda-container
      image: nvidia/cuda:13.0.2-runtime-ubuntu22.04
      command: ["/bin/sh", "-c"]
      args: ["nvidia-smi && sleep 300"]
      resources:
        limits:
          nvidia.com/gpu: 1
  tolerations:
    - key: "nvidia.com/gpu"
      operator: "Exists"                      # taint 값(bottlerocket)과 상관없이 허용
      effect: "NoSchedule"
EOF
kubectl wait --for=condition=Ready pod/gpu-pod-br --timeout=10m
kubectl logs gpu-pod-br
```

[예상 결과]
```
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 580.xx.xx              Driver Version: 580.xx.xx      CUDA Version: 13.0     |
...
|   0  NVIDIA L40S                    On  |   00000000:xx:00.0 Off |                    0 |
...
```

#### 3.2 노드 정보 ####
```
export NODE=$(kubectl get pod gpu-pod-br -o jsonpath='{.spec.nodeName}')
kubectl get nodes -l karpenter.sh/nodepool=gpu-optimized \
  -o custom-columns='NAME:.metadata.name,OS:.status.nodeInfo.osImage,RUNTIME:.status.nodeInfo.containerRuntimeVersion,GPU:.status.allocatable.nvidia\.com/gpu'
kubectl get node ${NODE} -o json \
  | jq -r '.status.capacity["ephemeral-storage"] | rtrimstr("Ki") | tonumber / 1048576 | floor | "ephemeral-storage: \(.)Gi"'
kubectl get node ${NODE} -o jsonpath='{.spec.taints}'; echo
```

[예상 결과]
```
NAME                                            OS                                             RUNTIME                           GPU
ip-10-0-xx-xx.ap-northeast-2.compute.internal   Bottlerocket OS 1.70.0 (aws-k8s-1.34-nvidia)   containerd://2.3.x+bottlerocket   1
ephemeral-storage: 558Gi
[{"effect":"NoSchedule","key":"nvidia.com/gpu","value":"bottlerocket"}]
```
- **GPU:** 1이면 Bottlerocket의 device plugin이 GPU를 등록한 것이다.
- **ephemeral-storage:** kubelet이 보는 노드 디스크 크기다. 약 558Gi(600GB)가 나오면 kubelet 디렉터리가 NVMe에 있는 것이다. 20Gi 안팎이 나오면 NVMe가 묶이지 않은 것이다(7절).

#### 3.3 nvdp 파드가 없는지 확인 ####
```
kubectl get pods -n nvidia -o wide --field-selector spec.nodeName=${NODE}
```

[예상 결과]
```
No resources found in nvidia namespace.
```
NFD worker, nvdp, GFD 파드가 하나라도 보이면 1절을 다시 확인한다.

#### 3.4 SOCI 설정 확인 ####
Bottlerocket의 control 컨테이너에서는 SSM 에이전트가 돈다. SSM Run Command로 보낸 명령은 이 컨테이너에서 실행된다. 여기서 `apiclient`로 노드 설정과 NVMe 디스크를 확인한다.
```
INSTANCE_ID=$(kubectl get node ${NODE} -o jsonpath='{.spec.providerID}' | awk -F/ '{print $NF}')
CMD_ID=$(aws ssm send-command --instance-ids ${INSTANCE_ID} \
  --document-name AWS-RunShellScript \
  --parameters 'commands=["apiclient get settings.container-runtime.snapshotter","apiclient get settings.container-runtime-plugins.soci-snapshotter","apiclient get settings.bootstrap-commands","apiclient ephemeral-storage list-disks"]' \
  --query Command.CommandId --output text)
aws ssm wait command-executed --command-id ${CMD_ID} --instance-id ${INSTANCE_ID}
aws ssm get-command-invocation --command-id ${CMD_ID} --instance-id ${INSTANCE_ID} \
  --query StandardOutputContent --output text
```

[예상 결과]
```
{
  "settings": {
    "container-runtime": {
      "snapshotter": "soci"
    }
  }
}
{
  "settings": {
    "container-runtime-plugins": {
      "soci-snapshotter": {
        "parallel-pull-unpack": {
          "concurrent-download-chunk-size": "16mb",
          "discard-unpacked-layers": true,
          "max-concurrent-downloads-per-image": 20,
          "max-concurrent-unpacks-per-image": 12
        },
        "pull-mode": "parallel-pull-unpack"
      }
    }
  }
}
{
  "settings": {
    "bootstrap-commands": {
      "000-mount-instance-storage": {
        "commands": [
          [
            "apiclient",
            "ephemeral-storage",
            "init"
          ],
          [
            "apiclient",
            "ephemeral-storage",
            "bind"
          ]
        ],
        "essential": true,
        "mode": "always"
      }
    }
  }
}
/dev/nvme1n1
```
- **기본값 키:** `max-concurrent-downloads`처럼 기본값이 있는 다른 키가 함께 나올 수 있다.
- **bind 명령:** `bind` 뒤에 `--dirs`가 없어야 SOCI 디렉터리까지 옮기는 기본 목록이 쓰인다.
- **디스크 이름:** 마지막 줄은 NVMe 디스크 목록이다. 디스크 이름은 다를 수 있다.
- **마운트 확인:** 실제 마운트를 보려면 6.2절처럼 admin 컨테이너에 들어가 `sudo sheltie` 뒤에 `findmnt /var/lib/soci-snapshotter`를 실행한다.

#### 3.5 테스트 노드 정리 ####
```
kubectl delete pod gpu-pod-br
kubectl delete nodeclaim -l karpenter.sh/nodepool=gpu-optimized
```
- **지우는 이유:** 4절에서 노드가 새로 뜨는 시간까지 재기 위해서다. 이미지 받는 시간만 볼 거라면 지우지 않고 4절로 넘어가도 된다. 비어 있는 노드는 20분 뒤 정리된다.

### 4. vLLM을 gpu-optimized로 옮기기 ###
4장 Deployment 매니페스트에서 nodeSelector의 노드풀 이름만 바꾼다. 그다음 같은 `kubectl apply`를 다시 실행한다. 매니페스트 안의 `${BUCKET}`, `${AWS_REGION}`이 치환되도록 이 변수가 설정된 셸에서 실행한다. 7장(KEDA)에서 `replicas`를 지웠다면 그 매니페스트를 쓴다.
```yaml
      nodeSelector:
        karpenter.sh/nodepool: gpu-optimized        # gpu → gpu-optimized (Bottlerocket + SOCI parallel pull)
        node.kubernetes.io/instance-type: g6e.4xlarge
```
```
kubectl rollout status deployment/gemma4-12b-vllm -n llm-serving --timeout=20m
kubectl get pods -n llm-serving -l app.kubernetes.io/name=gemma4-12b-vllm -o wide
```

[예상 결과]
```
deployment "gemma4-12b-vllm" successfully rolled out
NAME                               READY   STATUS    RESTARTS   AGE   IP           NODE                                            ...
gemma4-12b-vllm-6d9f8b7c5d-x2k4p   1/1     Running   0          6m    10.0.xx.xx   ip-10-0-xx-xx.ap-northeast-2.compute.internal   ...
```
- **롤링 업데이트:** maxSurge 1, maxUnavailable 0이다. 그래서 새 파드가 Ready가 될 때까지 기존 파드가 요청을 받는다. 새 파드가 뜰 gpu-optimized 노드가 하나 생긴다.
- **기존 노드:** 비게 된 `gpu` 노드는 `gpu` NodePool의 consolidateAfter(20분)가 지나면 정리된다.
- **NetworkPolicy:** 8장을 적용했다면 옮긴 뒤 8장 4절의 확인을 다시 한다. Bottlerocket 커널(6.12)은 VPC CNI 네트워크 정책의 요건(5.10 이상)을 만족한다.

### 5. 콜드 스타트 비교 ###
새 파드의 생성 시각, 노드 배정 시각, Ready 시각, kubelet 이벤트를 본다. 이벤트는 1시간 뒤 사라지므로 롤아웃 직후에 확인한다.
```
POD=$(kubectl get pods -n llm-serving -l app.kubernetes.io/name=gemma4-12b-vllm \
  --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1:].metadata.name}')
kubectl get pod ${POD} -n llm-serving -o json | jq -r '
  ["Created", .metadata.creationTimestamp],
  (.status.conditions[] | select(.type == "PodScheduled" or .type == "Ready") | [.type, .lastTransitionTime])
  | @tsv'
kubectl get events -n llm-serving --field-selector involvedObject.name=${POD} \
  -o custom-columns='TIME:.lastTimestamp,REASON:.reason,MESSAGE:.message'
```

[예상 결과]
```
Created        2026-11-24T09:00:00Z
PodScheduled   2026-11-24T09:01:xxZ
Ready          2026-11-24T09:0x:xxZ
TIME                   REASON    MESSAGE
...
2026-11-24T09:01:xxZ   Pulling   Pulling image "vllm/vllm-openai:v0.33.0"
2026-11-24T09:0x:xxZ   Pulled    Successfully pulled image "vllm/vllm-openai:v0.33.0" in <시간> (<시간> including waiting). Image size: <크기> bytes.
2026-11-24T09:0x:xxZ   Started   Started container vllm
```
구간은 다음처럼 계산해 4장 값과 비교한다.

| 구간 | 계산 | 4장 (gpu, AL2023) | gpu-optimized |
|---|---|---|---|
| 노드 | PodScheduled - Created | 65초 | 측정값 |
| 이미지 pull | Pulled 메시지의 시간 | 176초 | 측정값 |
| vLLM 기동 | Ready - Pulled 시각 | 193초 | 측정값 |

- **기대치:** SOCI 문서는 64코어 이상의 호스트를 권장한다. g6e.4xlarge는 16 vCPU라서 블로그 수치만큼 줄지 않을 수 있다. 그러니 직접 잰 값으로 판단한다.

### 6. 운영할 때 알아 둘 점 ###

#### 6.1 GPU 모니터링 (11장) ####
11장의 DCGM Exporter는 nodeSelector가 `karpenter.sh/nodepool: gpu`라서 새 노드에 뜨지 않는다. nodeSelector를 넓히는 것만으로도 부족하다. 이유는 다음과 같다.
- DCGM Exporter는 GPU를 요청하지 않고 `NVIDIA_VISIBLE_DEVICES` 환경 변수로 노드의 GPU를 본다.
- Bottlerocket은 권한 없는 컨테이너의 이 변수를 무시한다(`visible-devices-envvar-when-unprivileged` 기본값 false).
- 차트의 기본 securityContext는 privileged가 아니다.

그래서 지금은 다음 영향이 있다.
- **GPU 지표:** gpu-optimized 노드의 GPU 사용률, 온도, XID, ECC 지표가 없다. vLLM 지표는 파드에서 나오므로 KEDA 스케일링에는 영향이 없다.
- **GPUMetricsMissing:** 이 노드는 GPU가 있는데 DCGM 지표가 없다. 그래서 이 알림이 노드마다 10분 뒤 critical로 발생한다.
- **나머지 알림:** GPUAllocatableLessThanCapacity와 GPUNodeNotReady는 kube-state-metrics 지표를 쓰므로 그대로 동작한다.

Bottlerocket 노드에서 DCGM Exporter를 돌리기 전까지는 GPUMetricsMissing 식에서 Bottlerocket 노드를 뺀다. 11장 7절의 `gpu-alerts`에서 식을 아래처럼 바꾸고 다시 apply 한다. 이렇게 하면 이 노드에는 하드웨어 알림이 없다는 점을 알고 운영해야 한다.
```yaml
        - alert: GPUMetricsMissing
          expr: |
            kube_node_status_capacity{resource="nvidia_com_gpu"} > 0
            unless on (node) DCGM_FI_DEV_GPU_TEMP_CELSIUS
            unless on (node) kube_node_info{os_image=~"Bottlerocket.*"}
```

#### 6.2 노드 안 들여다보기 ####
Bottlerocket 호스트에는 셸이 없다. 그래서 11장 6.2절의 `kubectl debug node ... chroot /host sh`는 이 노드에서 동작하지 않는다. 대신 SSM 세션으로 control 컨테이너에 들어간다. admin 컨테이너는 필요할 때만 켠다.
```
INSTANCE_ID=$(kubectl get node ${NODE} -o jsonpath='{.spec.providerID}' | awk -F/ '{print $NF}')
aws ssm start-session --target ${INSTANCE_ID}
```
세션 안(control 컨테이너)에서 실행한다.
```
enter-admin-container                                    # admin 컨테이너를 켜고 들어간다
sudo sheltie                                             # 호스트 root 셸
journalctl -k | grep -i xid | tail -20                   # XID 확인
journalctl -u nvidia-k8s-device-plugin --no-pager | tail -20
exit                                                     # sheltie 종료
exit                                                     # admin 컨테이너에서 나온다
disable-admin-container                                  # 다 쓰면 끈다
```
- **admin 컨테이너:** 호스트 root 권한을 가진 컨테이너라 기본으로 꺼져 있다. 쓰고 나면 반드시 끈다.
- **GPU 상태:** `nvidia-smi`는 vLLM 파드 안에서 실행한다. 예: `kubectl exec -n llm-serving <파드> -- nvidia-smi -q -d ECC,TEMPERATURE,PERFORMANCE`
- **노드 교체:** cordon, KEDA 레플리카 고정, NodeClaim 삭제 순서는 11장 6.2절과 같다.

#### 6.3 그 밖의 차이 ####
- **AMI 올리기:** 환경 설정에서 `BOTTLEROCKET_VERSION`을 다시 구하고 2.1절 매니페스트를 다시 만들어 apply 한다. 기존 노드는 drift로 하나씩 교체되고, 그때 vLLM 파드도 다시 뜬다. userData, 블록 디바이스, `instanceStorePolicy`를 바꿀 때도 같다.
- **레지스트리:** parallel pull은 HTTP range GET으로 레이어를 나눠 받는다. ECR은 이를 지원한다. 4장 이미지(`vllm/vllm-openai`)는 Docker Hub에 있다. 받기가 실패하거나 느리면 `max-concurrent-downloads-per-image`를 낮추거나 ECR에 있는 이미지(예: AWS DLC vLLM 이미지)를 쓴다.
- **인스턴스 스토어 데이터:** 인스턴스를 중지하거나 종료하면 NVMe의 데이터는 지워진다. 노드가 새로 뜨면 이미지를 어차피 다시 받으므로 문제가 없다.
- **EBS와 비교:** AWS 문서에는 g6e.4xlarge NVMe의 무작위 IOPS(쓰기 40,000)만 있고 순차 처리량은 없다. 5절에서 잰 이미지 받기 시간이 기대보다 길면 데이터를 EBS에 두는 설정으로 바꿔 비교한다. 아래처럼 `instanceStorePolicy` 줄을 지우고 데이터 볼륨을 키운다. 이 설정은 노드마다 EBS IOPS와 처리량 요금이 추가로 든다. 이 값을 넣으면 g6e.4xlarge의 EBS 최대 처리량(1,000MB/s)까지 쓴다.
```yaml
  blockDeviceMappings:
    - deviceName: /dev/xvda
      ebs: {volumeSize: 4Gi, volumeType: gp3, encrypted: true}
    - deviceName: /dev/xvdb
      ebs: {volumeSize: 100Gi, volumeType: gp3, iops: 16000, throughput: 1000, encrypted: true}
```
- **노드풀 선택:** 노드풀을 지정하지 않은 GPU 파드(예: 3장의 `gpu-pod`)는 두 풀 중 어느 쪽에도 뜰 수 있다. 특정 풀에 띄우려면 nodeSelector에 `karpenter.sh/nodepool`을 지정한다.

### 7. 문제 해결 ###
| 증상 | 확인할 것 |
|---|---|
| `gpu-optimized` EC2NodeClass의 READY가 False다 | `kubectl describe ec2nodeclass gpu-optimized`의 Conditions를 본다. `AMIsReady`가 False면 alias의 버전이 이 리전에 없다. `aws ssm get-parameter --name /aws/service/bottlerocket/aws-k8s-${K8S_VERSION}-nvidia/x86_64/${BOTTLEROCKET_VERSION}/image_id`로 확인한다. |
| NodeClaim은 있는데 노드가 클러스터에 붙지 않는다 | `kubectl describe nodeclaim -l karpenter.sh/nodepool=gpu-optimized`의 Conditions를 본다. Launched가 False면 `kubectl logs -n karpenter deploy/karpenter`에서 오류를 찾는다. Launched인데 Registered가 되지 않으면 `aws ec2 get-console-output --instance-id <인스턴스 ID> --latest --output text`로 부팅 로그를 본다. NVMe 부팅 명령은 `essential = true`라서 실패하면 노드가 뜨지 않는다. |
| 노드의 ephemeral-storage가 20Gi 안팎이다 | NVMe가 묶이지 않은 것이다. 3.4절에서 `000-mount-instance-storage`가 있는지 본다. Bottlerocket 버전이 1.46.0 이상인지, 인스턴스에 NVMe가 있는지도 확인한다. |
| 노드는 Ready인데 GPU 수가 비어 있다 | 6.2절처럼 들어가 `journalctl -u nvidia-k8s-device-plugin`을 본다. |
| `nvidia` 네임스페이스 파드가 새 노드에 떠 있다 | 1절의 NFD worker toleration이 `Equal present`인지, 노드 taint 값이 `bottlerocket`인지 본다. |
| 이미지 받는 시간이 그대로다 | 3.4절로 snapshotter가 `soci`인지 본다. `kubectl get pod -o wide`로 파드가 gpu-optimized 노드에 떴는지도 본다. |
| vLLM 파드가 Pending이다 | `kubectl describe pod`의 Events와 Karpenter 로그를 본다. nodeSelector의 노드풀 이름과 GPU 할당량(vCPU 쿼터)을 확인한다. |

### 8. 정리 ###
먼저 vLLM을 `gpu` 풀로 되돌린다. 4장 매니페스트의 nodeSelector를 `gpu`로 바꿔 다시 apply 한 뒤 롤아웃을 기다린다.
```
kubectl rollout status deployment/gemma4-12b-vllm -n llm-serving --timeout=20m
kubectl delete pod gpu-pod-br --ignore-not-found
kubectl delete nodepool gpu-optimized          # 이 풀의 노드도 함께 종료된다
kubectl delete ec2nodeclass gpu-optimized
```
- **순서:** vLLM을 먼저 옮긴다. vLLM 파드가 gpu-optimized 노드에 있는 상태에서 NodePool을 지우면 노드가 종료되면서 서빙이 끊긴다. 새 파드도 nodeSelector에 맞는 풀이 없어 Pending이 된다.
- **알림 식:** 6.1절에서 GPUMetricsMissing 식을 바꿨다면 되돌린다.

## 참고자료 ##
* [Karpenter Blueprint: Using SOCI snapshotter parallel pull/unpack mode](https://aws-samples.github.io/karpenter-blueprints/blueprints/soci-snapshotter/)
* [Introducing Seekable OCI Parallel Pull mode for Amazon EKS (AWS 블로그)](https://aws.amazon.com/blogs/containers/introducing-seekable-oci-parallel-pull-mode-for-amazon-eks/)
* [SOCI snapshotter: Parallel Pull and Unpack Mode](https://github.com/awslabs/soci-snapshotter/blob/main/docs/parallel-mode.md)
* [Bottlerocket 설정: container-runtime-plugins](https://bottlerocket.dev/en/os/1.68.x/api/settings/container-runtime-plugins/)
* [Bottlerocket 설정: kubelet-device-plugins](https://bottlerocket.dev/en/os/1.68.x/api/settings/kubelet-device-plugins/)
* [Bottlerocket: Host Containers (SSM 접속)](https://bottlerocket.dev/en/os/1.68.x/install/quickstart/aws/host-containers/)
* [Bottlerocket 릴리스](https://github.com/bottlerocket-os/bottlerocket/releases)
* [Bottlerocket ephemeral-storage 구현](https://github.com/bottlerocket-os/bottlerocket-core-kit/blob/develop/sources/api/apiserver/src/server/ephemeral_storage.rs)
* [Karpenter v1.8 NodeClasses 문서](https://github.com/aws/karpenter-provider-aws/blob/v1.8.1/website/content/en/v1.8/concepts/nodeclasses.md)
* [Karpenter v1.8.1 Bottlerocket 부트스트랩 코드 (instanceStorePolicy 처리)](https://github.com/aws/karpenter-provider-aws/blob/v1.8.1/pkg/providers/amifamily/bootstrap/bottlerocket.go)
* [NVIDIA k8s-device-plugin 차트 values (v0.20.2)](https://github.com/NVIDIA/k8s-device-plugin/blob/v0.20.2/deployments/helm/nvidia-device-plugin/values.yaml)
* [Amazon EKS: 네트워크 정책 요건](https://docs.aws.amazon.com/eks/latest/userguide/cni-network-policy-configure.html)
* [Amazon EC2 가속 컴퓨팅 인스턴스 사양](https://docs.aws.amazon.com/ec2/latest/instancetypes/ac.html)
