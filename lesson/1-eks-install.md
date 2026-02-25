### VPC 생성하기 ###
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
