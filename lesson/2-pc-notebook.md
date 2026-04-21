## GPU 할당 및 주피터 노트북 설정 ##

### 1. [g7e.4xlarge](https://aws.amazon.com/ko/ec2/instance-types/g7e/) 인스턴스 생성 ###
```
export CLUSTER_NAME=eks-agentic-ai
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export TOKEN=$(curl -sX PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
export AWS_REGION=$(curl -sH "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/region)
export KEY_NAME="aws-kp-2"
export INSTANCE_TYPE="g7e.4xlarge"

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
export PUBLIC_SUBNET_ID=$(aws ec2 describe-subnets \
  --filters "Name=vpc-id,Values=${VPC_ID}" \
  --query 'Subnets[?MapPublicIpOnLaunch==`true`] | [0].SubnetId' --output text)

echo "AMI_ID: $AMI_ID"
echo "SG_ID: $SG_ID"
echo "PUBLIC_SUBNET_ID: $PUBLIC_SUBNET_ID"
```
g7e.4xlarge 인스턴스를 퍼블릭 서브넷에 생성한다. 우분투 22.04 이미지이고 nvidia 드라이버 및 pytroch 환경이 이미 설정되어 있다.
```
aws ec2 run-instances --image-id ${AMI_ID} \
  --instance-type ${INSTANCE_TYPE} \
  --key-name ${KEY_NAME} \
  --subnet-id ${PUBLIC_SUBNET_ID} \
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
  ]' \
  --tag-specifications '[
    {
      "ResourceType": "instance",
      "Tags": [
        {"Key": "Name", "Value": "gpu-dev"}
      ]
    },
    {
      "ResourceType": "volume",
      "Tags": [
        {"Key": "Name", "Value": "gpu-dev"}
      ]
    }
  ]'
```

> [!TIP]
> 인스턴스 삭제
> ```
> aws ec2 terminate-instances \
>  --region ${AWS_REGION} \
>  --instance-ids $(aws ec2 describe-instances \
>    --filters \
>      "Name=tag:Name,Values=gpu-dev" \
>      "Name=instance-state-name,Values=pending,running,stopped,stopping" \
>    --query 'Reservations[].Instances[].InstanceId' \
>    --output text \
>    --region ${AWS_REGION})
> ```




### 2. PC 의 VS-CODE 로 접속하기 ###
이 방식은 로컬 PC 의 vs-code IDE 에서 리모트 서버로 ssh 로 접속하여 주피터 노트북을 실행하는 방법이다.

`~/.ssh/config 파일에 추가`:
```
Host gpu-dev
  HostName <EC2-IP>
  User ubuntu
  IdentityFile <KeyFile Path>
```

1. `Ctrl+Shift+P → "Remote-SSH: Connect to Host" → gpu-dev 선택`

2. `VS Code에서 Jupyter 확장 설치`: 
   Extensions 탭 → "Jupyter" 검색 → Install in SSH

3. `노트북 파일 생성`: 
   Ctrl+Shift+P → "Create: New Jupyter Notebook"
 
4. `커널 선택`: 
   우측 상단 "Select Kernel" 클릭
   → "Python Environments" → gpu-dev (~/gpu-dev/bin/python)

5. `GPU 및 CUDA 버전 등을 확인` 

![](https://github.com/gnosia93/agentic-ai-eks/blob/main/lesson/images/vscode-jupyter-2.png)

### 3. 주피터 노트북에 접속하기 (Optional) ###
ssh 로 로그인 한 후 아래 명령어를 실행하고, 웹 브라우저를 이용하여 해당 서버의 8080 포트로 접속한다. 
```
jupyter lab --ip=0.0.0.0 --port=8080 --no-browser --NotebookApp.token='' --NotebookApp.password=''
```
![](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/images/jupyter-notebook.png)
