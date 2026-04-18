### s3 버킷생성 ###
```
export CLUSTER_NAME=eks-agentic-ai
export BUCKET_NAME=${CLUSTER_NAME}-vectordb-milvus

aws s3 mb s3://${BUCKET_NAME} --region ap-northeast-2
```

### milvus 설치 ###
```
helm repo add milvus https://zilliz.github.io/milvus-helm/
helm repo update
helm install milvus milvus/milvus \
  --set cluster.enabled=true \
  --set externalS3.enabled=true \
  --set externalS3.host=s3.amazonaws.com \
  --set externalS3.bucketName=<your-bucket> \
  --set externalS3.useIAM=true \
  --set minio.enabled=false \
  -n milvus --create-namespace
```
