S3 Express One Zone을 쓰려면 디렉터리 버킷을 만든다.
```
# 디렉터리 버킷을 둘 AZ ID (AZ 이름이 아닌 ID). S3 Express One Zone을 지원하는 AZ만 쓸 수 있습니다.
#   예: us-east-1 → use1-az4, use1-az5, use1-az6 / ap-northeast-2 → apne2-az3
export S3_AZ_ID="apne2-az3"

# 디렉터리 버킷 이름은 <기본 이름>--<AZ ID>--x-s3 형식이며, 전체 63자 이하여야 합니다
export BUCKET="${CLUSTER_NAME:?}-${AWS_ACCOUNT_ID:?}--${S3_AZ_ID:?}--x-s3"

# 버킷 생성 (디렉터리 버킷은 리전과 관계없이 LocationConstraint 대신 Location과 Bucket을 지정합니다)
aws s3api create-bucket \
  --bucket "$BUCKET" \
  --region "$AWS_REGION" \
  --create-bucket-configuration "Location={Type=AvailabilityZone,Name=${S3_AZ_ID}},Bucket={DataRedundancy=SingleAvailabilityZone,Type=Directory}"

# 생성 확인
aws s3api head-bucket --bucket "$BUCKET" --region "$AWS_REGION"
```
S3_AZ_ID는 쓰는 리전에 맞게 바꿔야 한다. 지원하는 AZ는 리전마다 정해져 있고, 서울 리전은 apne2-az3 하나뿐이다.


* IAM 정책: 디렉터리 버킷은 s3: 액션 대신 s3express:CreateSession 하나로 객체 읽기와 목록 조회 권한을 준다.
  ARN 형식도 달라서 vLLM 파드 IAM 역할의 정책을 아래처럼 바꿔야 모델을 읽을 수 있다.
```
{
  "Effect": "Allow",
  "Action": "s3express:CreateSession",
  "Resource": "arn:aws:s3express:${AWS_REGION}:${AWS_ACCOUNT_ID}:bucket/${BUCKET}"
}
```

* GPU 노드 AZ: 버킷이 AZ 하나에만 있으니 GPU 노드도 같은 AZ에 둬야 지연이 가장 작다. (다른 AZ에서도 읽을 수는 있다) 

* VPC 엔드포인트: 노드가 프라이빗 서브넷에서 NAT를 통해 나간다면 com.amazonaws.<리전>.s3express 게이트웨이 엔드포인트를 추가한다. 이 엔드포인트는 기존 S3 게이트웨이 엔드포인트(com.amazonaws.<리전>.s3)와 별개라서, 추가하지 않으면 디렉터리 버킷 트래픽이 NAT를 사용한다.





