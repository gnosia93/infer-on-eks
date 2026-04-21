## GPU 할당 및 주피터 노트북 설정 ##

### 1. [g7e.4xlarge](https://aws.amazon.com/ko/ec2/instance-types/g7e/) 인스턴스 생성 ###
```
export KEY_NAME="aws-kp-2"
export INSTANCE_TYPE="g7e.4xlarge"
export CLUSTER_NAME=eks-agentic-ai
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export TOKEN=$(curl -sX PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
export INSTANCE_ID=$(curl -sH "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/instance-id)
export VPC_ID=$(aws ec2 describe-instances --instance-ids $INSTANCE_ID \
  --query 'Reservations[0].Instances[0].VpcId' --output text)
export AWS_REGION=$(curl -sH "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/region)

export AMI_ID=$(aws ec2 describe-images --owners amazon \
  --filters "Name=name,Values=Deep Learning OSS Nvidia Driver AMI GPU PyTorch*Ubuntu 22.04*" \
  --query 'sort_by(Images, &CreationDate)[-1].[ImageId]' --output text --region $AWS_REGION)
export SG_ID=$(aws ec2 describe-security-groups --filters \
  "Name=group-name,Values=eks-host-sg" "Name=vpc-id,Values=${VPC_ID}" \
  --query 'SecurityGroups[0].GroupId' --output text)
export PUBLIC_SUBNET_ID=$(aws ec2 describe-subnets \
  --filters "Name=vpc-id,Values=${VPC_ID}" \
  --query 'Subnets[?MapPublicIpOnLaunch==`true`] | [0].SubnetId' --output text)

echo ""
echo "CLUSTER_NAME: $CLUSTER_NAME"
echo "ACCOUNT_ID: $ACCOUNT_ID"
echo "AWS_REGION: $AWS_REGION"
echo "VPC_ID: $VPC_ID"
echo "AMI_ID: $AMI_ID"
echo "SG_ID: $SG_ID"
echo "PUBLIC_SUBNET_ID: $PUBLIC_SUBNET_ID"
```
g7e.4xlarge 인스턴스를 퍼블릭 서브넷에 생성한다. 우분투 22.04 이미지이고 nvidia 드라이버 및 pytroch 환경이 이미 설정되어 있다.
```
INSTANCE_ID=$(aws ec2 run-instances --image-id ${AMI_ID} \
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
  ]' \
  --query 'Instances[0].InstanceId' \
  --output text)

echo "INSTANCE_ID=$INSTANCE_ID"
echo "Waiting for EC2 DNS assigning ..."
sleep 30
echo "INSTANCE_DNS: $(aws ec2 describe-instances --instance-ids $INSTANCE_ID --region $AWS_REGION \
  --query 'Reservations[0].Instances[0].PublicDnsName' --output text)"
```
생성된 EC2 인스턴스의 AMI 는 `Deep Learning OSS Nvidia Driver AMI GPU PyTorch 2.7 (Ubuntu 22.04)` 에 해당하는 것으로 `source /opt/pytorch/bin/activate` 를 이용하여 pytorch 가상환경을 활성화 할 수 있다. 활성화 이후 아래 파일을 이용하여 Nvidia CUDA 라이브러리가 제대로 로딩되는 지 확인한다. 최초 실행지 libtorch_cuda.so, libcudnn*.so, libnccl.so 와 같은 라이브러리들의 심볼릭 링크를 생성하므로 첫 실행의 경우 2분 이상의 시간이 소요될 수 있다.  
```
cat > /tmp/check.py <<'EOF'
import torch
print('torch:', torch.__version__)
print('cuda available:', torch.cuda.is_available())
print('cuda version:', torch.version.cuda)
print('device count:', torch.cuda.device_count())
print('device name:', torch.cuda.get_device_name(0))
EOF

python /tmp/check.py
```


> [!TIP]
> 인스턴스 삭제
> ```
> aws ec2 terminate-instances --instance-ids $INSTANCE_ID --region $AWS_REGION
> ```

### 2. PC 의 VS-CODE 로 접속하기 ###
이 방식은 로컬 PC 의 vs-code IDE 에서 리모트 서버로 ssh 로 접속하여 주피터 노트북을 실행하는 방법이다.

`~/.ssh/config 파일에 추가`:
```
Host gpu-dev
  HostName <EC2-IP or DNS>
  User ubuntu
  IdentityFile <KeyFile Path>
```

1. ssh 로 EC2 인스턴스에 로그인하여 아래 명령어를 실행한다. (~/.bashrc 파일에 activate 및 ipykernel 명령어 추가한다)
```
echo 'source /opt/pytorch/bin/activate' >> ~/.bashrc
echo 'python -m ipykernel install --user --name pytorch --display-name "Python (pytorch)"' >> ~/.bashrc

#source /opt/pytorch/bin/activate
#pip install ipykernel
#jupyter kernelspec list
``` 

2. VS Code 에서 `Ctrl+Shift+P → "Remote-SSH: Connect to Host" → gpu-dev 선택 → continue 선택`
   
![](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/images/vscode-remote-ssh.png)

3. `VS Code에서 Jupyter 확장 설치`: 
   Extensions 탭 → "Jupyter" 검색 → Install in SSH

3. `노트북 파일 생성`: 
   Ctrl+Shift+P → "Create: New Jupyter Notebook"
 
4. `커널 선택`: 
   우측 상단 "Detecting Kernels" → Jupyter Kernel... → Python (pytorch) (Python 3.12.10) 선택
 
5. `GPU 및 CUDA 버전 등을 확인` 

![](https://github.com/gnosia93/agentic-ai-eks/blob/main/lesson/images/vscode-jupyter-2.png)

### 3. 주피터 노트북에 접속하기 (Optional) ###
ssh 로 로그인 한 후 아래 명령어를 실행하고, 웹 브라우저를 이용하여 해당 서버의 8080 포트로 접속한다. 
```
jupyter lab --ip=0.0.0.0 --port=8080 --no-browser --NotebookApp.token='' --NotebookApp.password=''
```
![](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/images/jupyter-notebook.png)
