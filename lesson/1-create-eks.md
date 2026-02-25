## VPC 생성하기 ##
로컬 PC에 [테라폼을 설치](https://developer.hashicorp.com/terraform/tutorials/aws-get-started/install-cli)한 후 다음 명령어로 AWS VPC 를 생성한다. 
```bash
git clone https://github.com/gnosia93/infer-on-eks.git
cd ~/infer-on-eks/iac/tf

terraform init
terraform apply --auto-approve
```

[결과]
```
...
Outputs:

vscode_url = "http://ec2-3-38-209-255.ap-northeast-2.compute.amazonaws.com:8080"
```

## [kubectl 및 eksctl 설치](https://docs.aws.amazon.com/ko_kr/eks/latest/userguide/install-kubectl.html#linux_arm64_kubectl) ##

vscode_url 웹으로 접속한 후, 터미널을 열어 kubectl, eksctl, helm 을 설치한다.
![](https://github.com/gnosia93/training-on-eks/blob/main/chapter/images/code-server.png)
 
#### 1. kubectl 설치 #### 
```
ARCH=amd64     
curl -O https://s3.us-west-2.amazonaws.com/amazon-eks/1.33.3/2025-08-03/bin/linux/$ARCH/kubectl
chmod +x ./kubectl
mkdir -p $HOME/bin && cp ./kubectl $HOME/bin/kubectl && export PATH=$HOME/bin:$PATH
echo 'export PATH=$HOME/bin:$PATH' >> ~/.bashrc

kubectl version --client
```

#### 2. eksctl 설치 ####
```
ARCH=amd64    
PLATFORM=$(uname -s)_$ARCH
curl -sLO "https://github.com/eksctl-io/eksctl/releases/latest/download/eksctl_$PLATFORM.tar.gz"

tar -xzf eksctl_$PLATFORM.tar.gz -C /tmp && rm eksctl_$PLATFORM.tar.gz
sudo install -m 0755 /tmp/eksctl /usr/local/bin && rm /tmp/eksctl

eksctl version
```

#### 3. helm 설치 ####
```
curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-4
sh get_helm.sh

helm version
``` 

#### 4. k9s 설치 ####
```
ARCH="arm64"
if [ "$(uname -m)" != 'aarch64' ]; then
  ARCH="amd64"
fi
echo ${ARCH}" architecture detected .."
curl --silent --location "https://github.com/derailed/k9s/releases/latest/download/k9s_Linux_${ARCH}.tar.gz" | tar xz -C /tmp
sudo mv /tmp/k9s /usr/local/bin/
k9s version
```

#### 5. eks-node-viewer 설치 ####
```
sudo dnf update -y
sudo dnf install golang -y

# 설치 확인 (v1.11 이상 필요)
go version
go install github.com/awslabs/eks-node-viewer/cmd/eks-node-viewer@latest

echo 'export PATH=$PATH:$(go env GOPATH)/bin' >> ~/.bashrc
source ~/.bashrc
```
go 컴파일 과정에서 다소 시간이 소요된다.

## EKS 생성하기 ##

### 1. 환경 설정 ###
```
export AWS_REGION=$(aws ec2 describe-availability-zones --query 'AvailabilityZones[0].RegionName' --output text)
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export CLUSTER_NAME="infer-on-eks"
export K8S_VERSION="1.34"
export KARPENTER_VERSION="1.8.1"
export VPC_ID=$(aws ec2 describe-vpcs --filters Name=tag:Name,Values="${CLUSTER_NAME}" --query "Vpcs[].VpcId" --output text)

echo ${AWS_REGION}
echo ${AWS_ACCOUNT_ID}
echo ${CLUSTER_NAME}
echo ${KARPENTER_VERSION}
echo ${VPC_ID}
```
환경변수 값이 제대로 출력되는지 확인한다.  

### 2. 서브넷 식별 ###
클러스터의 데이터 플레인(워커노드 들)은 아래의 프라이빗 서브넷에 위치하게 된다. 
```
aws ec2 describe-subnets \
    --filters "Name=tag:Name,Values=INF-priv-subnet-*" "Name=vpc-id,Values=${VPC_ID}" \
    --query "Subnets[*].{ID:SubnetId, AZ:AvailabilityZone, Name:Tags[?Key=='Name']|[0].Value}" \
    --output table

SUBNET_IDS=$(aws ec2 describe-subnets \
    --filters "Name=tag:Name,Values=INF-priv-subnet-*" "Name=vpc-id,Values=${VPC_ID}" \
    --query "Subnets[*].{ID:SubnetId, AZ:AvailabilityZone}" \
    --output text)

if [ -z "$SUBNET_IDS" ]; then
    echo "에러: VPC ${VPC_ID} 에 서브넷이 존재하지 않습니다.."
fi

# YAML 형식에 맞게 동적 문자열 생성 (각 ID 뒤에 ": {}" 추가 및 앞쪽 Identation과 줄바꿈)
SUBNET_YAML=""
if [ -f SUBNET_IDS ]; then
    rm SUBNET_IDS
fi
echo "$SUBNET_IDS" | while read -r az subnet_id;
do
    echo "      ${az}: { id: ${subnet_id} }" >> SUBNET_IDS
done
```

### 3. 클러스터 생성 ### 
클러스터 생성 완료까지 약 20 ~ 30분 정도의 시간이 소요된다.
```
cat > cluster.yaml <<EOF 
apiVersion: eksctl.io/v1alpha5
kind: ClusterConfig
metadata:
  name: "${CLUSTER_NAME}"
  version: "${K8S_VERSION}"
  region: "${AWS_REGION}"
  tags:
    karpenter.sh/discovery: "${CLUSTER_NAME}"    # 이 태그가 있어야 Karpenter가 서브넷/보안그룹을 자동으로 찾습니다.
  
vpc:
  id: "${VPC_ID}"                    
  subnets:
    private:                                 # 프라이빗 서브넷에 데이터플레인 설치
$(cat SUBNET_IDS)

addons:
  - name: vpc-cni
    podIdentityAssociations:
      - serviceAccountName: aws-node
        namespace: kube-system
        permissionPolicyARNs: 
          - arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy
  - name: eks-pod-identity-agent
  - name: metrics-server
  - name: kube-proxy
  - name: coredns
  - name: aws-ebs-csi-driver                 # loki-ng 용  

managedNodeGroups:                           # 관리형 노드 그룹 
  - name: ng-x86
    instanceType: c6i.2xlarge
    minSize: 2
    maxSize: 2
    desiredCapacity: 2
    amiFamily: AmazonLinux2023
    privateNetworking: true           		 # 이 노드 그룹이 PRIVATE 서브넷만 사용하도록 지정합니다. 
    iam:
      withAddonPolicies:
        ebs: true                     		 # EBS CSI 드라이버가 작동하기 위한 IAM 권한 부여

iam:
  withOIDC: true 

karpenter:
  version: "${KARPENTER_VERSION}"
  createServiceAccount: true 				 # IRSA를 자동으로 생성하여 Karpenter Pod에 할당
EOF
```
```
eksctl create cluster -f cluster.yaml
```

[결과]
```
2026-02-25 13:28:10 [ℹ]  eksctl version 0.223.0
2026-02-25 13:28:10 [ℹ]  using region ap-northeast-2
2026-02-25 13:28:10 [✔]  using existing VPC (vpc-04fbb67959873f927) and subnets (private:map[ap-northeast-2a:{subnet-09725f2afc4621bfd ap-northeast-2a 10.0.10.0/24 0 } ap-northeast-2b:{subnet-0196a83087a6425b4 ap-northeast-2b 10.0.11.0/24 0 }] public:map[])
2026-02-25 13:28:10 [!]  custom VPC/subnets will be used; if resulting cluster doesn't function as expected, make sure to review the configuration of VPC/subnets
2026-02-25 13:28:10 [ℹ]  nodegroup "ng-x86" will use "" [AmazonLinux2023/1.34]
2026-02-25 13:28:10 [!]  Auto Mode will be enabled by default in an upcoming release of eksctl. This means managed node groups and managed networking add-ons will no longer be created by default. To maintain current behavior, explicitly set 'autoModeConfig.enabled: false' in your cluster configuration. Learn more: https://eksctl.io/usage/auto-mode/
2026-02-25 13:28:10 [ℹ]  using Kubernetes version 1.34
2026-02-25 13:28:10 [ℹ]  creating EKS cluster "infer-on-eks" in "ap-northeast-2" region with managed nodes
2026-02-25 13:28:10 [ℹ]  1 nodegroup (ng-x86) was included (based on the include/exclude rules)
2026-02-25 13:28:10 [ℹ]  will create a CloudFormation stack for cluster itself and 1 managed nodegroup stack(s)
2026-02-25 13:28:10 [ℹ]  if you encounter any issues, check CloudFormation console or try 'eksctl utils describe-stacks --region=ap-northeast-2 --cluster=infer-on-eks'
2026-02-25 13:28:10 [ℹ]  Kubernetes API endpoint access will use default of {publicAccess=true, privateAccess=false} for cluster "infer-on-eks" in "ap-northeast-2"
2026-02-25 13:28:10 [ℹ]  CloudWatch logging will not be enabled for cluster "infer-on-eks" in "ap-northeast-2"
2026-02-25 13:28:10 [ℹ]  you can enable it with 'eksctl utils update-cluster-logging --enable-types={SPECIFY-YOUR-LOG-TYPES-HERE (e.g. all)} --region=ap-northeast-2 --cluster=infer-on-eks'
2026-02-25 13:28:10 [ℹ]  
2 sequential tasks: { create cluster control plane "infer-on-eks", 
    2 sequential sub-tasks: { 
        5 sequential sub-tasks: { 
            1 task: { create addons },
            wait for control plane to become ready,
            associate IAM OIDC provider,
            no tasks,
            update VPC CNI to use IRSA if required,
        },
        create managed nodegroup "ng-x86",
    }
...


```

EKS 에서 클러스터 시큐리티 그룹은 컨트롤 플레인과 워커노드 사이의 통신을 가능하게 한다. 컨트롤 플레인은 10250 포트를 통해 노드의 큐블렛과 통신하고 워커노드는 443 포트를 이용하여 컨트롤 플레인의 API 서버에 접근을 시도한다. 아래 명령어는 클러스터 시큐리티 그룹에 "karpenter.sh/discovery=${CLUSTER_NAME}" 태크가 존재하는지 확인하는 스크립트이다. 카펜터가 노드를 생성할때, 이와 동일한 태크를 가진 시큐리티 그룹을 찾아 신규 노드에 할당하게 된다. 시큐리티 그룹 검색에 실패하게 되는 경우, EC2 인스턴스는 생성되지만 EKS 클러스터에 조인하지 못한다.  

```
aws ec2 create-tags \
  --resources $(aws eks describe-cluster --name ${CLUSTER_NAME} --query \
					"cluster.resourcesVpcConfig.clusterSecurityGroupId" --output text) \
  --tags Key=karpenter.sh/discovery,Value=${CLUSTER_NAME}
```

```
aws ec2 describe-security-groups \
  --group-ids $(aws eks describe-cluster --name ${CLUSTER_NAME} --query \
					"cluster.resourcesVpcConfig.clusterSecurityGroupId" --output text) \
  --query "SecurityGroups[0].Tags" \
  --output table
```
[결과]
```
----------------------------------------------------------------------------------------
|                                DescribeSecurityGroups                                |
+----------------------------------------+---------------------------------------------+
|                   Key                  |                    Value                    |
+----------------------------------------+---------------------------------------------+
|  kubernetes.io/cluster/training-on-eks |  owned                                      |
|  Name                                  |  eks-cluster-sg-training-on-eks-1860330510  |
|  aws:eks:cluster-name                  |  training-on-eks                            |
|  karpenter.sh/discovery                |  training-on-eks                            |
+----------------------------------------+---------------------------------------------+
```

### 추가 정책 설정 ###
클러스터 생성이 완료되면 추가 설정이 필요하다. 카펜터 버전 1.8.1(EKS 1.3.4) 에는 아래와 같은 정책 설정이 누락되어 있어 패치가 필요하다. 
패치를 하지 않는 경우 카펜터가 프러비저닝한 노드가 클러스터에 조인되지 않는다. (노드 describe 시 Not Ready 상태)  

* eksctl-training-on-eks-iamservice-role 에 정책 추가(OIDC 정책 누락)
```
POLICY_JSON=$(cat <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "VisualEditor0",
            "Effect": "Allow",
            "Action": "eks:DescribeCluster",
            "Resource": "arn:aws:eks:${AWS_REGION}:${AWS_ACCOUNT_ID}:cluster/${CLUSTER_NAME}"
        },
        {
            "Effect": "Allow",
            "Action": [
                "iam:CreateInstanceProfile",
                "iam:DeleteInstanceProfile",
                "iam:GetInstanceProfile",
                "iam:TagInstanceProfile",
                "iam:AddRoleToInstanceProfile",
                "iam:RemoveRoleFromInstanceProfile",
                "iam:ListInstanceProfiles"
            ],
            "Resource": "*"
        }
    ]
}
EOF
)

aws iam put-role-policy \
    --role-name eksctl-training-on-eks-iamservice-role \
    --policy-name EKS_OIDC_Support_Policy \
    --policy-document "$POLICY_JSON"
```




