### [테라폼 설치](https://developer.hashicorp.com/terraform/install) ###
mac 의 경우 아래의 명령어로 설치할 수 있다. 
```
brew tap hashicorp/tap
brew install hashicorp/tap/terraform
```

### EKS 설치 ###
```
git clone https://github.com/gnosia93/eks-agentic-ai.git
cd eks-agentic-ai/iac/tf

terraform init
terraform apply -auto-approve
```

### 클러스터 등록 ###

eai-vscode 웹 콘솔로 로그인하여 아래 명령어를 실행한다.
```
export CLUSTER_NAME=eks-agentic-ai
aws eks update-kubeconfig --name ${CLUSTER_NAME}

# Karpenter 설치
#helm install karpenter oci://public.ecr.aws/karpenter/karpenter \
#  --namespace karpenter --create-namespace \
#  --set settings.clusterName=${var.cluster_name} \
#  --set settings.clusterEndpoint=$(aws eks describe-cluster --name ${var.cluster_name} --query "cluster.endpoint" --output text) \
#  --set serviceAccount.annotations."eks\.amazonaws\.com/role-arn"=${karpenter_role_arn}
```


### EKS 삭제 ###
워크샵과 관련된 리소스를 모두 삭제한다.
```
terraform destroy --auto-approve
```


