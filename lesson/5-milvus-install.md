### 1. s3 버킷확인 ###
테라폼에서 milvus 용으로 생성한 버킷 확인한다. 
```bash
export CLUSTER_NAME=eks-agentic-ai
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export TOKEN=$(curl -sX PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
export AWS_REGION=$(curl -sH "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/region)
export VECTORDB_BUCKET_NAME=${CLUSTER_NAME}-vectordb-milvus-${ACCOUNT_ID}
export MILVUS_ROLE_ARN=arn:aws:iam::${ACCOUNT_ID}:role/${CLUSTER_NAME}-milvus

echo "CLUSTER_NAME: $CLUSTER_NAME"
echo "ACCOUNT_ID: $ACCOUNT_ID"
echo "AWS_REGION: $AWS_REGION"
echo "VECTORDB_BUCKET_NAME: ${VECTORDB_BUCKET_NAME}"
echo "MILVUS_ROLE_ARN: ${MILVUS_ROLE_ARN}"

aws s3 ls | grep ${VECTORDB_BUCKET_NAME}
```

### 2. milvus 설치 ###
eks 클러스터에 milvus 를 설치한다.
```bash
helm repo add milvus https://zilliztech.github.io/milvus-helm/
helm repo update

# ============================================
# Milvus 설치 (Standalone + S3 + RocksMQ)
# ============================================
helm upgrade --install milvus milvus/milvus \
  --namespace milvus --create-namespace \
  --set cluster.enabled=false \
  --set pulsarv3.enabled=false \
  --set pulsar.enabled=false \
  --set kafka.enabled=false \
  --set minio.enabled=false \
  --set etcd.replicaCount=1 \
  --set standalone.messageQueue=rocksmq \
  --set externalS3.enabled=true \
  --set externalS3.host=s3.${AWS_REGION}.amazonaws.com \
  --set externalS3.port=443 \
  --set externalS3.bucketName=${VECTORDB_BUCKET_NAME} \
  --set externalS3.rootPath=files \
  --set externalS3.useIAM=true \
  --set externalS3.cloudProvider=aws \
  --set externalS3.useSSL=true \
  --set serviceAccount.create=true \
  --set serviceAccount.name=milvus-sa \
  --set serviceAccount.annotations."eks\.amazonaws\.com/role-arn"=${MILVUS_ROLE_ARN}
```

> [!TIP]
> 설치된 helm 레포지토리 리스트를 확인한다.
> ```
> helm repo list
> ```
> [결과]
> ```
> NAME    URL                                      
> nvidia  https://helm.ngc.nvidia.com/nvidia       
> eks     https://aws.github.io/eks-charts         
> milvus  https://zilliztech.github.io/milvus-helm/
> ```
> 헬름 릴리즈(milvus) 삭제
> ```
> helm uninstall milvus -n milvus
> ```

### 3. milvus 설치 확인 ###
```bash
kubectl get pods -n milvus
```
[결과]
```
NAME                                 READY   STATUS    RESTARTS   AGE
milvus-etcd-0                        1/1     Running   0          103s
milvus-standalone-855bbfd867-s5pgz   1/1     Running   0          103s
```
1/1/ READY 상태로 변경될때 까지 약 90초 정도의 시간이 소요된다.

## 테스트 ##
Milvus는 gRPC(19530)와 HTTP(9091) 두 가지 포트를 노출한다.

```bash
kubectl port-forward svc/milvus -n milvus 19530:19530 &

mkdir milvus && cd milvus
pip install "pymilvus>=2.5.0"

curl -o milvus-test.py \
https://raw.githubusercontent.com/gnosia93/eks-agentic-ai/refs/heads/main/code/rag/milvus-test.py

python3 milvus-test.py

kill %1
```





