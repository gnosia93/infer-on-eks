## GPU 스케줄링 ##

쿠버네티스는 기본적으로 CPU와 메모리만 인식해 스케줄링하며, GPU 같은 특수 하드웨어는 알지 못합니다. GPU는 쿠버네티스에서 확장 리소스(extended resource)로 취급되는데, 이를 스케줄러가 사용할 수 있게 노출해 주는 것이 바로 NVIDIA 디바이스 플러그인입니다. 디바이스 플러그인은 DaemonSet 형태로 각 노드에 배포되어 노드에 장착된 GPU를 자동으로 탐지하고, 이를 nvidia.com/gpu라는 할당 가능한 리소스로 kubelet에 등록합니다. 또한 파드가 GPU를 할당받을 때 필요한 디바이스 파일과 드라이버를 컨테이너에 연결해 주는 역할도 담당합니다.

따라서 디바이스 플러그인이 없으면 쿠버네티스는 노드에 GPU가 있다는 사실 자체를 알지 못하기 때문에, 파드가 nvidia.com/gpu 리소스를 요청해도 스케줄링되지 못하고 Pending 상태에 머무릅니다. 위 설치에서 함께 활성화한 GPU Feature Discovery(gfd.enabled=true)는 GPU 모델명이나 메모리 크기 같은 정보를 노드 레이블로 추가해, 특정 GPU 타입을 지정해 스케줄링하는 등 더 세밀한 배치를 가능하게 해 줍니다.

### 1. 디바이스 플러그인 설치 ###
```
helm repo add nvdp https://nvidia.github.io/k8s-device-plugin
helm repo update
helm search repo nvdp --devel

helm install nvdp nvdp/nvidia-device-plugin \
  --namespace nvidia \
  --create-namespace \
  --version 0.18.2 \
  --set gfd.enabled=true

kubectl get daemonset -n nvidia
```

### 2. GPU 노드풀 생성 ###
```
cat <<EOF > nodepool-gpu.yaml 
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: gpu
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
      nodeClassRef:
        group: karpenter.k8s.aws
        kind: EC2NodeClass
        name: gpu
      expireAfter: 720h # 30 * 24h = 720h
      taints:
      - key: "nvidia.com/gpu"            # nvidia-device-plugin 데몬은 nvidia.com/gpu=present:NoSchedule 테인트를 Tolerate 한다. 
        value: "present"                 # value 값으로 present 와 다른값을 설정하면 nvidia-device-plugin 이 동작하지 않는다 (GPU를 찾을 수 없다)   
        effect: NoSchedule               # nvidia-device-plugin 이 GPU 를 찾으면 Nvidia GPU 관련 각종 테인트와 레이블 등을 노드에 할당한다.  
  limits:
    cpu: 1000
  disruption:
    consolidationPolicy: WhenEmpty       # 이전 설정값은 WhenEmptyOrUnderutilized / 노드의 잦은 Not Ready 상태로의 변경으로 인해 수정  
    consolidateAfter: 20m
---
apiVersion: karpenter.k8s.aws/v1
kind: EC2NodeClass
metadata:
  name: gpu
spec:
  role: "eksctl-KarpenterNodeRole-${CLUSTER_NAME}"
  amiSelectorTerms:
    # Required; when coupled with a pod that requests NVIDIA GPUs or AWS Neuron
    # devices, Karpenter will select the correct AL2023 accelerated AMI variant
    # see https://aws.amazon.com/ko/blogs/containers/amazon-eks-optimized-amazon-linux-2023-accelerated-amis-now-available/
    # EKS GPU Optimized AMI: NVIDIA 드라이버와 CUDA 런타임만 포함된 가벼운 이미지 (Karpenter가 자동으로 선택 가능) 가 설치됨.
    # 특정 DLAMI 가 필요한 경우 - name : 필드에 정의해야 함. 
    - alias: al2023@latest
  subnetSelectorTerms:
    - tags:
        karpenter.sh/discovery: "${CLUSTER_NAME}" 
  securityGroupSelectorTerms:
    - tags:
        karpenter.sh/discovery: "${CLUSTER_NAME}" 
  blockDeviceMappings:
    - deviceName: /dev/xvda
      ebs:
        volumeSize: 600Gi
        volumeType: gp3
EOF

kubectl apply -f nodepool-gpu.yaml
```
Ready 상태값이 True 임을 확인한다. 
```
kubectl get ec2nodeclass,nodepool
```
[결과]
```
NAME                                 READY   AGE
ec2nodeclass.karpenter.k8s.aws/gpu   True    17s

NAME                        NODECLASS   NODES   READY   AGE
nodepool.karpenter.sh/gpu   gpu         0       True    17s
```

### 3. nvidia-smi 파드 스케줄링 ###
```
cat <<EOF | kubectl apply -f - 
apiVersion: v1
kind: Pod
metadata:
  name: gpu-pod
spec:
  restartPolicy: Never                                # 재시작 정책을 Never로 설정 (실행 완료 후 다시 시작하지 않음)
  containers:                                         # 기본값은 Always - 컨테이너가 성공적으로 종료(exit 0)되든, 에러로 종료(exit nonzero)되든 상관없이 항상 재시작
    - name: cuda-container                            # nvidia-smi만 실행하고 끝나는 파드에 이 정책이 적용되면, 종료 후 다시 실행을 반복하다가 결국 CrashLoopBackOff 상태가 됨.
      image: nvidia/cuda:13.0.2-runtime-ubuntu22.04    
      command: ["/bin/sh", "-c"]
      args: ["nvidia-smi && sleep 300"]                # nvidia-smi 실행 후 300초(5분) 동안 대기
      resources:
        limits:
          nvidia.com/gpu: 1
  tolerations:                                             
    - key: "nvidia.com/gpu"
      operator: "Exists"                      # 노드의 테인트는 nvidia.com/gpu=present:NoSchedule 이나,   
      effect: "NoSchedule"                    # Exists 연산자로 nvidia.com/gpu 키만 체크         
EOF
```

파드를 생성하고 nvidia-smi 가 동작하는지 확인한다. 파드의 상태는 Pending -> Container Creating -> Running 상태로 바뀐다.
```
kubectl get pods
```
[결과]
```
NAME      READY   STATUS    RESTARTS   AGE
gpu-pod   1/1     Running   0          3m59s
```
gpu-pod 의 로그를 조회한다.
```
kubectl logs gpu-pod
```
[출력]
```
Wed Dec 10 06:44:46 2025       
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 570.195.03             Driver Version: 570.195.03     CUDA Version: 13.0     |
|-----------------------------------------+------------------------+----------------------+
| GPU  Name                 Persistence-M | Bus-Id          Disp.A | Volatile Uncorr. ECC |
| Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |
|                                         |                        |               MIG M. |
|=========================================+========================+======================|
|   0  NVIDIA T4G                     On  |   00000000:00:1F.0 Off |                    0 |
| N/A   49C    P8              9W /   70W |       0MiB /  15360MiB |      0%      Default |
|                                         |                        |                  N/A |
+-----------------------------------------+------------------------+----------------------+
                                                                                         
+-----------------------------------------------------------------------------------------+
| Processes:                                                                              |
|  GPU   GI   CI              PID   Type   Process name                        GPU Memory |
|        ID   ID                                                               Usage      |
|=========================================================================================|
|  No running processes found                                                             |
+-----------------------------------------------------------------------------------------+
```

vs-code 웹콘솔에서 새로운 터미널을 하나 열어서 eks-node-viwer 를 실행한다. 
![](https://github.com/gnosia93/vlm-distillation/blob/main/images/eks-node-view-nvidia-smi.png)


## EFA 활성화 ##

EFA(Elastic Fabric Adapter)는 AWS가 제공하는 고성능 네트워크 인터페이스로, 여러 노드에 걸친 분산 학습처럼 노드 간에 대량의 데이터를 빠르게 주고받아야 하는 워크로드를 위해 설계되었습니다. 일반적인 네트워크는 운영체제 커널을 거쳐 통신하지만, EFA는 OS 커널을 우회해 애플리케이션이 네트워크 하드웨어와 직접 통신하는 OS-bypass 방식을 사용합니다. 덕분에 지연 시간이 크게 줄고 대역폭이 높아져, NCCL 기반의 GPU 간 집합 통신(collective communication)처럼 노드 간 동기화가 빈번한 대규모 학습에서 통신 병목을 완화해 줍니다.

다만 쿠버네티스는 GPU와 마찬가지로 EFA 디바이스도 기본적으로 인식하지 못합니다. 그래서 각 노드의 EFA 인터페이스를 탐지해 vpc.amazonaws.com/efa라는 할당 가능한 리소스로 노출해 주는 EFA 디바이스 플러그인이 필요합니다. 이 플러그인 역시 DaemonSet 형태로 배포되어, 파드가 EFA 리소스를 요청하면 해당 디바이스를 컨테이너에 연결해 줍니다. 위 설치 명령에서 tolerations에 {"operator": "Exists"}를 추가한 것은, GPU 노드에 걸린 taint와 무관하게 플러그인 DaemonSet이 모든 노드에 배포되도록 하기 위함입니다.

### 1. EFA 플러그인 설치 ###
```
helm repo add eks https://aws.github.io/eks-charts
helm install aws-efa-k8s-device-plugin eks/aws-efa-k8s-device-plugin --namespace kube-system

kubectl patch ds aws-efa-k8s-device-plugin -n kube-system --type='json' -p='[
  {"op": "add", "path": "/spec/template/spec/tolerations/-", "value": {"operator": "Exists"}}
]'

kubectl get ds aws-efa-k8s-device-plugin -n kube-system
```

### 2. EFA 테스트 ###
```
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: efa-test-pod
  labels:
    app: efa-test
spec:
  nodeSelector:
    karpenter.sh/nodepool: gpu                
  tolerations:                                             
    - key: "nvidia.com/gpu"
      operator: "Exists"                      # 노드의 테인트는 nvidia.com/gpu=present:NoSchedule 이나, Exists 연산자로 nvidia.com/gpu 키만 체크  
      effect: "NoSchedule"
#    - key: "vpc.amazon.com/efa"              # 카펜터 gpu 풀의 노드들은 nvidia.com/gpu 테인트만 가지고 있다.
#      operator: "Exists"                       
#      effect: "NoSchedule"        
  containers:
    - name: efa-container                               # public.ecr.aws/deep-learning-containers/pytorch-training:2.8.0-gpu-py312-cu129-ubuntu22.04-ec2-v1.0 
      image: public.ecr.aws/hpc-cloud/nccl-tests:latest           # EFA 드라이버와 NCCL 테스트 도구가 포함된 이미지 사용 (NVIDIA 공식 이미지 권장)
      command: ["/bin/bash", "-c", "sleep infinity"]
      resources:
        limits:
          vpc.amazonaws.com/efa: 1                      # EFA 장치를 파드에 직접 할당 (VPC CNI가 이 장치를 인식함)
          nvidia.com/gpu: 1                             # GPU 인스턴스인 경우
      securityContext:
        capabilities:                                   # EFA 통신을 위해 메모리 잠금 권한 필요
          add: ["IPC_LOCK"]
EOF
```
아래 명령어로 efa-test-pod 가 EFA 지원노드에 스케줄링 된 것을 확인 한 후 (Running), 
```
kubectl get pods
```
[결과]
```
NAME           READY   STATUS      RESTARTS   AGE
efa-test-pod   1/1     Running     0          3m20s
gpu-pod        0/1     Completed   0          17m
```

efa-test-pod 파드에 로그인하여 efa 디바이스 정보를 조회한다. 
```
kubectl exec -it efa-test-pod -- /bin/bash
fi_info -p efa
ls -la /sys/class/infiniband/
```

[결과]
```
root@efa-test-pod:/# fi_info -p efa
provider: efa
    fabric: efa-direct
    domain: rdmap47s0-rdm
    version: 204.0
    type: FI_EP_RDM
    protocol: FI_PROTO_EFA
provider: efa
    fabric: efa
    domain: rdmap47s0-rdm
    version: 204.0
    type: FI_EP_RDM
    protocol: FI_PROTO_EFA
provider: efa
    fabric: efa
    domain: rdmap47s0-dgrm
    version: 204.0
    type: FI_EP_DGRAM
    protocol: FI_PROTO_EFA
root@efa-test-pod:/# ls -la /sys/class/infiniband/
total 0
drwxr-xr-x.  2 root root 0 Jul 24 17:43 .
drwxr-xr-x. 40 root root 0 Jul 24 17:43 ..
lrwxrwxrwx.  1 root root 0 Jul 24 17:43 rdmap47s0 -> ../../devices/pci0000:24/0000:24:00.0/0000:25:00.0/0000:26:01.0/0000:2f:00.0/infiniband/rdmap47s0
```

## CloudWatch Container Insight ##

cloudwatch 파드를 조회한다. 
```
kubectl get pods -n amazon-cloudwatch
```
[결과]
```
NAME                                                              READY   STATUS    RESTARTS   AGE
amazon-cloudwatch-observability-controller-manager-57c8c8cxwwsf   1/1     Running   0          16m
cloudwatch-agent-szbrk                                            1/1     Running   0          16m
cloudwatch-agent-twm82                                            1/1     Running   0          16m
cloudwatch-agent-wwnph                                            1/1     Running   0          6m39s
dcgm-exporter-wvqrz                                               1/1     Running   0          6m39s
fluent-bit-nwgkb                                                  1/1     Running   0          16m
fluent-bit-p8mw8                                                  1/1     Running   0          16m
fluent-bit-qz6nd                                                  1/1     Running   0          6m39s
```

vs-code 웹 콘솔에서 새로운 터미널을 하나 열고 파드 / 컨테이너 로그를 조회한다. 
```
export AWS_REGION=$(aws ec2 describe-availability-zones --query 'AvailabilityZones[0].RegionName' --output text)
export CLUSTER_NAME="vlm-distillation"


QID=$(aws logs start-query \
  --region $AWS_REGION \
  --log-group-name "/aws/containerinsights/$CLUSTER_NAME/application" \
  --start-time $(date -d '1 hour ago' +%s) \
  --end-time $(date +%s) \
  --query-string 'fields @timestamp, kubernetes.pod_name, log | filter kubernetes.pod_name like "mnist-ddp-node" | sort @timestamp asc | limit 300' \
  --query queryId --output text)

sleep 6
aws logs get-query-results --region $AWS_REGION --query-id "$QID"
```

> [!NOTE]
> logs:FilterLogEvents 권한 오류 발생시 아래 명령어 실행.
> ```
> aws iam attach-role-policy \
> --role-name VlmEKS_Role \
> --policy-arn arn:aws:iam::aws:policy/CloudWatchLogsReadOnlyAccess
> ```

## _(Optional)_ 볼륨 스냅샷 CSI 드라이버 설치 ##

볼륨 스냅샷은 CSI(Container Storage Interface) 표준으로 PVC(영구 볼륨)의 특정 시점 상태를 스냅샷으로 떠서 나중에 복원하거나 복제하는 기능입니다. 
```
SNAP_VERSION=v8.2.0   # v8.x 중 최신 태그로 (snapshotter v8.6과 호환)

# 1) 스냅샷 CRD 3종
kubectl apply -k "https://github.com/kubernetes-csi/external-snapshotter/client/config/crd?ref=${SNAP_VERSION}"
