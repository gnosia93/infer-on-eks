### [테라폼 설치](https://developer.hashicorp.com/terraform/install) ###
mac 의 경우 아래의 명령어로 설치할 수 있다. 
```
brew tap hashicorp/tap
brew install hashicorp/tap/terraform
```

### EKS 설치 ###
테라폼으로 VPC 및 접속용 vs-code EC2 인스턴스를 생성한다.   
```
git pull https://github.com/gnosia93/eks-agentic-ai.git
cd eks-agentic-ai/tf

terraform init
terraform apply -auto-approve
```

### Karpenter 설치 ###

gpu-vscode 웹 콘솔로 로그인하여 아래 명령어를 실행한다.
```
# kubeconfig 설정
aws eks update-kubeconfig --name ${var.cluster_name}

# Karpenter 설치
helm install karpenter oci://public.ecr.aws/karpenter/karpenter \
  --namespace karpenter --create-namespace \
  --set settings.clusterName=${var.cluster_name} \
  --set settings.clusterEndpoint=$(aws eks describe-cluster --name ${var.cluster_name} --query "cluster.endpoint" --output text) \
  --set serviceAccount.annotations."eks\.amazonaws\.com/role-arn"=${karpenter_role_arn}
```
variables.tf에 cluster_name 변수가 이미 있으니 그대로 쓰면 된다.


### EKS 삭제 ###
워크샵과 관련된 리소스를 모두 삭제한다.
```
terraform destroy --auto-approve
```


