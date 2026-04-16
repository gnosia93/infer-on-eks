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
aws configure set region ap-northeast-2

aws eks update-kubeconfig --name ${CLUSTER_NAME}

# Karpenter 설치
#helm install karpenter oci://public.ecr.aws/karpenter/karpenter \
#  --namespace karpenter --create-namespace \
#  --set settings.clusterName=${var.cluster_name} \
#  --set settings.clusterEndpoint=$(aws eks describe-cluster --name ${var.cluster_name} --query "cluster.endpoint" --output text) \
#  --set serviceAccount.annotations."eks\.amazonaws\.com/role-arn"=${karpenter_role_arn}
```
kubectl를 설치한다.
```
ARCH=amd64
curl -O https://s3.us-west-2.amazonaws.com/amazon-eks/1.33.3/2025-08-03/bin/linux/$ARCH/kubectl
chmod +x ./kubectl
mkdir -p $HOME/bin && cp ./kubectl $HOME/bin/kubectl && export PATH=$HOME/bin:$PATH
echo 'export PATH=$HOME/bin:$PATH' >> ~/.bashrc

kubectl version --client
```

### 카펜터 설치 확인 ###
본 워크샵에서는 테라폼 apply 시 eks 클러스터와 함께 카펜터가 자동으로 설치된다. 하지만 노드풀 및 ec2노드 클래스는 별도로 생성해야 한다. 
```
kubectl get pods -n karpenter -l app.kubernetes.io/name=karpenter
kubectl get crd | grep karpenter

kubectl logs -n karpenter -l app.kubernetes.io/name=karpenter --tail=50
```

### 관리용 소프트웨어 설치 ###
```
curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-4
sh get_helm.sh
helm version

ARCH="arm64"
if [ "$(uname -m)" != 'aarch64' ]; then
  ARCH="amd64"
fi
echo ${ARCH}" architecture detected .."
curl --silent --location "https://github.com/derailed/k9s/releases/latest/download/k9s_Linux_${ARCH}.tar.gz" | tar xz -C /tmp
sudo mv /tmp/k9s /usr/local/bin/
k9s version

sudo dnf update -y
sudo dnf install golang -y
go version
go install github.com/awslabs/eks-node-viewer/cmd/eks-node-viewer@latest

echo 'export PATH=$PATH:$(go env GOPATH)/bin' >> ~/.bashrc
source ~/.bashrc
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

### gpu 풀 생성 ###

