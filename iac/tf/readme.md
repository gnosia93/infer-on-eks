### [테라폼 설치](https://developer.hashicorp.com/terraform/install) ###
mac 의 경우 아래의 명령어로 설치할 수 있다. 
```
brew tap hashicorp/tap
brew install hashicorp/tap/terraform
```

### EKS 설치 ###
karpenter helm 차트가 aws ecr 에 있기 때문에 ecr 로 먼저 로그인 한 후 설치한다.
```
git clone https://github.com/gnosia93/eks-agentic-ai.git
cd eks-agentic-ai/iac/tf

aws ecr-public get-login-password --region us-east-1 | \
 helm registry login --username AWS --password-stdin public.ecr.aws

terraform init
terraform apply --auto-approve
```
> [!NOTE]
> 클러스터 삭제:
> 
> terraform destroy --auto-approve


### 클러스터 등록 ###

eai-vscode 웹 콘솔로 로그인하여 아래 명령어를 실행한다.
```
export CLUSTER_NAME=eks-agentic-ai
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export TOKEN=$(curl -sX PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
export AWS_REGION=$(curl -sH "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/region)

echo "CLUSTER_NAME: $CLUSTER_NAME"
echo "ACCOUNT_ID: $ACCOUNT_ID"
echo "AWS_REGION: $AWS_REGION"

aws eks update-kubeconfig --name ${CLUSTER_NAME} --region ${AWS_REGION}
```

### 관리용 소프트웨어 설치 ###
```
ARCH=amd64
curl -O https://s3.us-west-2.amazonaws.com/amazon-eks/1.33.3/2025-08-03/bin/linux/$ARCH/kubectl
chmod +x ./kubectl
mkdir -p $HOME/bin && cp ./kubectl $HOME/bin/kubectl && export PATH=$HOME/bin:$PATH
echo 'export PATH=$HOME/bin:$PATH' >> ~/.bashrc
kubectl version --client

curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-4
bash get_helm.sh
helm version

curl --silent --location "https://github.com/derailed/k9s/releases/latest/download/k9s_Linux_${ARCH}.tar.gz" | tar xz -C /tmp
sudo mv /tmp/k9s /usr/local/bin/
k9s version
```
```
wget https://go.dev/dl/go1.24.4.linux-amd64.tar.gz
sudo rm -rf /usr/local/go
sudo tar -C /usr/local -xzf go1.24.4.linux-amd64.tar.gz
echo 'export PATH=/usr/local/go/bin:$PATH:$(go env GOPATH)/bin' >> ~/.bashrc
source ~/.bashrc
go version

sudo apt update -y
sudo apt install -y golang
go version
go install github.com/awslabs/eks-node-viewer/cmd/eks-node-viewer@latest
echo 'export PATH=$PATH:$(go env GOPATH)/bin' >> ~/.bashrc
source ~/.bashrc
```

### 카펜터 설치 확인 ###
본 워크샵에서는 테라폼 apply 시 eks 클러스터와 함께 카펜터가 자동으로 설치된다. 하지만 노드풀 및 ec2노드 클래스는 별도로 생성해야 한다. 
```
kubectl get pods -n karpenter -l app.kubernetes.io/name=karpenter
kubectl get crd | grep karpenter

kubectl logs -n karpenter -l app.kubernetes.io/name=karpenter --tail=50
```

### 메트릭 서버 설치 ###
파드의 CPU 및 메모리 사용량 정보를 추적하기 위해서 메트릭 서버를 설치한다.
```
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
```


### GPU 오퍼레이터 설치 ###
EKS GPU AMI에는 이미 NVIDIA 드라이버와 NVIDIA 컨테이너 툴킷이 설치되어 있어서, GPU Operator에서 이 부분을 비활성화해야 한다.

```
helm repo add nvidia https://helm.ngc.nvidia.com/nvidia
helm repo update

helm install gpu-operator nvidia/gpu-operator \
  --namespace gpu-operator \
  --create-namespace \
  --set driver.enabled=false \
  --set toolkit.enabled=false \
  --set devicePlugin.enabled=true \
  --set migManager.enabled=false \
  --set mig.strategy=single

# Pod 상태 확인
kubectl get pods -n gpu-operator
kubectl get nodes -o json | jq '.items[].status.allocatable["nvidia.com/gpu"]'
```

### EFA 설치 ###
```
helm repo add eks https://aws.github.io/eks-charts
helm install aws-efa-k8s-device-plugin eks/aws-efa-k8s-device-plugin --namespace kube-system

kubectl patch ds aws-efa-k8s-device-plugin -n kube-system --type='json' -p='[
  {"op": "add", "path": "/spec/template/spec/tolerations/-", "value": {"operator": "Exists"}}
]'

kubectl get ds aws-efa-k8s-device-plugin -n kube-system
```

### GPU 풀 생성 ###
```
kubectl apply -f - <<'EOF'
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
  role: "eks-agentic-ai-eks-node-role"
  amiSelectorTerms:
    # Required; when coupled with a pod that requests NVIDIA GPUs or AWS Neuron
    # devices, Karpenter will select the correct AL2023 accelerated AMI variant
    # see https://aws.amazon.com/ko/blogs/containers/amazon-eks-optimized-amazon-linux-2023-accelerated-amis-now-available/
    # EKS GPU Optimized AMI: NVIDIA 드라이버와 CUDA 런타임만 포함된 가벼운 이미지 (Karpenter가 자동으로 선택 가능) 가 설치됨.
    # 특정 DLAMI 가 필요한 경우 - name : 필드에 정의해야 함. 
    - alias: al2023@latest
  subnetSelectorTerms:
    - tags:
        karpenter.sh/discovery: "eks-agentic-ai" 
  securityGroupSelectorTerms:
    - tags:
        karpenter.sh/discovery: "eks-agentic-ai" 
  blockDeviceMappings:
    - deviceName: /dev/xvda
      ebs:
        volumeSize: 1000Gi
        volumeType: gp3
EOF
```
>[!NOTE]
> aws iam list-roles --query "Roles[?contains(RoleName, 'eks-agentic-ai')].RoleName"
>
> eks-agentic-ai-eks-cluster-role — EKS 컨트롤 플레인이 사용하는 Role. AWS가 관리하는 마스터 노드가 이 Role로 K8s API 서버, etcd 등을 운영  
> eks-agentic-ai-eks-node-role — 워커 노드(EC2)가 사용하는 Role. 노드가 EKS 클러스터에 조인하고, ECR에서 이미지 풀하고, VPC CNI 플러그인 동작하는 데 필요  
> eks-agentic-ai-karpenter-controller — Karpenter 컨트롤러 Pod가 사용하는 Role (IRSA). EC2 인스턴스 생성/삭제, 서브넷/보안그룹 조회 등 Karpenter가 노드를 프로비저닝하기 위한 권한  
>

생성된 노드풀과 ec2 노드클래스가 True 상태인지를 확인한다.
```
kubectl get ec2nodeclass,nodepool
```

### GPU 파드 테스트 ###
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
파드를 확인한다.
```
kubectl get pods
kubectl logs gpu-pod
```
[결과]
```
Thu Apr 16 09:19:26 2026       
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 580.126.09             Driver Version: 580.126.09     CUDA Version: 13.0     |
+-----------------------------------------+------------------------+----------------------+
| GPU  Name                 Persistence-M | Bus-Id          Disp.A | Volatile Uncorr. ECC |
| Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |
|                                         |                        |               MIG M. |
|=========================================+========================+======================|
|   0  Tesla T4                       On  |   00000000:00:1E.0 Off |                    0 |
| N/A   33C    P8             17W /   70W |       0MiB /  15360MiB |      0%      Default |
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
