1. S3 버킷 생성
모델 가중치를 저장할 S3 버킷을 생성한다.

```
export BUCKET="${CLUSTER_NAME:?}-${AWS_ACCOUNT_ID:?}"

# 버킷 생성 (us-east-1 외 리전은 LocationConstraint가 필요합니다)
aws s3api create-bucket \
  --bucket "$BUCKET" \
  --region "$AWS_REGION" \
  --create-bucket-configuration LocationConstraint="$AWS_REGION"

# 생성 확인
aws s3api head-bucket --bucket "$BUCKET"
```
