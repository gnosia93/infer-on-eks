### s3 버킷확인 ###
테라폼에서 milvus 용으로 생성한 버킷 확인한다. 
```
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

aws s3 ls | grep ${VECTORDB_BUCKET_NAME}
```

### CSI 드라이버 확인 ###
테라폼에서 설치한 CSI 드라라이버 및 스토리지 클래스를 확인한다. 

#### 1. 스토리지 클래스 조회 ####
```
kubectl get sc
```
[결과]
```
NAME            PROVISIONER             RECLAIMPOLICY   VOLUMEBINDINGMODE      ALLOWVOLUMEEXPANSION   AGE
gp2             kubernetes.io/aws-ebs   Delete          WaitForFirstConsumer   false                  22m
gp3 (default)   ebs.csi.aws.com         Delete          WaitForFirstConsumer   true                   17m
```
#### 2. EBS CSI 드라이버 확인 ###
```
kubectl get pods -n kube-system | grep ebs-csi
```
[결과]
```
ebs-csi-controller-85fd97c85b-glnbc   6/6     Running   0          19m
ebs-csi-controller-85fd97c85b-v7h86   6/6     Running   0          19m
ebs-csi-node-48h59                    3/3     Running   0          19m
ebs-csi-node-c6fmt                    3/3     Running   0          19m
ebs-csi-node-f46xd                    3/3     Running   0          3m26s
```

#### 3. addon 확인 ###
```
aws eks list-addons --cluster-name ${CLUSTER_NAME} --region ${AWS_REGION} --output text
```
[결과]
```
ADDONS  aws-ebs-csi-driver
```

### milvus 설치 ###
eks 클러스터에 milvus 를 설치한다.
```
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


### milvus 설치 확인 ###
```
kubectl get all -n milvus
```



### IRSA ##
```
EKS에서 useIAM=true 쓰려면
IRSA 설정이 되어 있어야 합니다:

OIDC Provider가 EKS 클러스터에 연결되어 있어야 하고
S3 접근 권한이 있는 IAM Role을 만들고
해당 Role을 Milvus ServiceAccount에 annotate

kubectl annotate serviceaccount milvus \
  -n milvus \
  eks.amazonaws.com/role-arn=arn:aws:iam::<ACCOUNT_ID>:role/<ROLE_NAME>
```

## 테스트 ##
Milvus는 gRPC(19530)와 HTTP(9091) 두 가지 포트를 노출한다.

#### port-forward ####
```
kubectl port-forward svc/milvus -n milvus 19530:19530
```

### 코드실행 ###

```
from pymilvus import connections, Collection, FieldSchema, CollectionSchema, DataType

connections.connect(host="localhost", port="19530")

fields = [
    FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
    FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=128)
]
schema = CollectionSchema(fields)
collection = Collection("test_collection", schema)
```

#### 1. 더미 백터(128차원) 생성 및 DB 입력 ####
```
import random
vectors = [[random.random() for _ in range(128)] for _ in range(10)]
collection.insert([vectors])
```

#### 2. 인덱스 생성 & 로드 ####
Milvus는 검색 성능을 위해 메모리에 올라와 있는 인덱스만 검색한다. 아래 load() 함수는 해당 collection을 메모리로 올리는 함수이다.

```
collection.create_index("embedding", {"index_type": "HNSW", "metric_type": "L2", "params": {"M": 8, "efConstruction": 64}})
collection.load()
```

#### 3. 백터 검색 ####
```
results = collection.search(
    data=[vectors[0]],
    anns_field="embedding",
    param={"metric_type": "L2", "params": {"ef": 10}},
    limit=5
)
print(results)
```



