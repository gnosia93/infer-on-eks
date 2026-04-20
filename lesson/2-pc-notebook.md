### [g7e.4xlarge](https://aws.amazon.com/ko/ec2/instance-types/g7e/) 인스턴스 생성 ##

환경 변수를 설정한다. 
```
export CLUSTER_NAME=eks-agentic-ai
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export TOKEN=$(curl -sX PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
export AWS_REGION=$(curl -sH "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/region)
export VPC_ID=$(curl -sH "X-aws-ec2-metadata-token: $TOKEN" \
  http://169.254.169.254/latest/meta-data/network/interfaces/macs/${MAC}/vpc-id)
export KEY_NAME="aws-kp-2"

echo "CLUSTER_NAME: $CLUSTER_NAME"
echo "ACCOUNT_ID: $ACCOUNT_ID"
echo "AWS_REGION: $AWS_REGION"
echo "VPC_ID: $VPC_ID"

export AMI_ID=$(aws ssm get-parameter \
  --name /aws/service/deeplearning/ami/x86_64/base-oss-nvidia-driver-gpu-ubuntu-22.04/latest/ami-id \
  --region ${AWS_REGION} --query 'Parameter.Value' --output text)

export SG_ID=$(aws ec2 describe-security-groups --filters \
  "Name=group-name,Values=eks-host-sg" "Name=vpc-id,Values=${VPC_ID}" \
  --query 'SecurityGroups[0].GroupId' --output text)

export SUBNET_ID=$()
```

```
aws ec2 run-instances \
  --image-id ${AMI_ID} \
  --instance-type g7e.4xlarge \
  --key-name ${KEY_NAME} \
  --subnet-id ${SUBNET_ID} \
  --security-group-ids ${SG_ID} \
  --associate-public-ip-address \
  --count 1 \
  --region ${AWS_REGION} \
  --block-device-mappings '[
    {
      "DeviceName": "/dev/sda1",
      "Ebs": {
        "VolumeSize": 300,
        "VolumeType": "gp3",
        "Iops": 3000,
        "Throughput": 125,
        "DeleteOnTermination": true,
        "Encrypted": true
      }
    }
  ]' 
```

















vscode 서버에는 이미 Jupyter, pytorch 등의 ML 개발 환경이 모두 설정되어져 있다. 

### 주피터 노트북 실행하기 ###
vscode 터미널에서 아래 명령어를 실행한 후, 브라우저의 새창을 띄운후 8080 포트로 접속한다.
```
jupyter lab --ip=0.0.0.0 --port=8080 --no-browser --NotebookApp.token='' --NotebookApp.password=''
```
![](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/images/jupyter-notebook.png)


### 참고 - PC 의 VS CODE 설정 ###
이 방식은 로컬 PC 의 vs code 에서 리모트에 있는 vscode 서버로 ssh 로 접속하여 주피터 노트북을 실행하는 방법이다.
```
~/.ssh/config 파일에 추가:

Host gpu-dev
  HostName 43.203.228.244
  User ubuntu
  IdentityFile ~/aws-kp2.pem
그 다음:

Ctrl+Shift+P → "Remote-SSH: Connect to Host" → gpu-dev 선택
```
```
1. VS Code에서 Jupyter 확장 설치
   Extensions 탭 → "Jupyter" 검색 → Install in SSH

2. 노트북 파일 생성
   Ctrl+Shift+P → "Create: New Jupyter Notebook"
   또는 파일 탐색기에서 test.ipynb 생성

3. 커널 선택
   우측 상단 "Select Kernel" 클릭
   → "Python Environments" → gpu-dev (~/gpu-dev/bin/python)

4. GPU 및 CUDA 버전 등을 확인한다. 
```
![](https://github.com/gnosia93/agentic-ai-eks/blob/main/lesson/images/vscode-jupyter-2.png)
