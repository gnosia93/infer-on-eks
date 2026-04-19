## RAGSearch MCP 서버 배포 (EKS) ##

RAGSearch를 MCP 서버로 감싸 EKS에 Pod로 배포한다. 외부 에이전트는 MCP 클라이언트로 Tool을 호출해 논문 검색 및 답변 생성을 원격으로 사용할 수 있다.

![](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/images/rag-mcp-arch.png)

### [1. rag_mcp_server.py 내려받기](https://github.com/gnosia93/eks-agentic-ai/blob/main/code/rag/rag-mcp-server.py) ###

```bash
curl -o rag_mcp_server.py \
https://raw.githubusercontent.com/gnosia93/eks-agentic-ai/refs/heads/main/code/rag/rag-mcp-server.py
```

`MILVUS_HOST` 기본값은 `milvus.milvus.svc.cluster.local`로, 같은 클러스터 내부에서 Milvus에 바로 접근한다.

> [!NOTE]
> 쿠버네티스(Kubernetes) 내부 DNS 형식  
> `<service-name>.<namespace>.svc.cluster.local`


### 2. Docker 이미지 빌드 ###

`requirements.txt`:
```bash
cat << 'EOF' > requirements.txt
mcp>=1.0.0
pymilvus>=2.4.0
sentence-transformers>=3.0.0
langchain
langchain-community
pymupdf
boto3
EOF
```

`Dockerfile`:
```bash
cat << 'EOF' > Dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 모델을 이미지에 포함해 Pod 시작 시간 단축
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; \
    SentenceTransformer('BAAI/bge-m3'); \
    CrossEncoder('BAAI/bge-reranker-v2-m3')"

COPY RAGSearch.py rag_mcp_server.py ./

EXPOSE 8000
CMD ["python", "rag_mcp_server.py"]
EOF
```
도커 이미지 크기가 좀 크다(모델 2개 약 4GB). 프로덕션에서는 PVC로 모델을 분리하는 방법도 있다.

### 3. ECR 푸시 ###

```bash
export CLUSTER_NAME=eks-agentic-ai
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export TOKEN=$(curl -sX PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
export AWS_REGION=$(curl -sH "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/region)

echo "CLUSTER_NAME: ${CLUSTER_NAME}"
echo "ACCOUNT_ID: ${ACCOUNT_ID}"
echo "AWS_REGION: ${AWS_REGION}"

aws ecr create-repository --repository-name rag-mcp --region ${AWS_REGION}

aws ecr get-login-password --region ${AWS_REGION} | \
  docker login --username AWS --password-stdin \
  ${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

docker build -t rag-mcp:latest .
docker tag rag-mcp:latest ${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/rag-mcp:latest
docker push ${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/rag-mcp:latest
```
도커 이미지 빌드에 10분 그리고 PUSH 에 2분 정도의 시간이 소요된다.

### 4. EKS 배포 ###

#### 4.1 Bedrock 접근 권한 (IRSA) ####

`iam-policy.json`:
```bash
cat << 'EOF' > iam-policy.json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
       "bedrock:InvokeModel",
       "bedrock:InvokeModelWithResponseStream",
       "bedrock:Converse",
       "bedrock:ConverseStream"
    ],
    "Resource": "*"
  }]
}
EOF
```

```bash
aws iam create-policy \
  --policy-name RAGMCPBedrockAccess \
  --policy-document file://iam-policy.json

eksctl create iamserviceaccount \
  --cluster=${CLUSTER_NAME} \
  --namespace=rag \
  --name=rag-mcp-sa \
  --attach-policy-arn=arn:aws:iam::${ACCOUNT_ID}:policy/RAGMCPBedrockAccess \
  --approve

kubectl get sa rag-mcp-sa -n rag
```
> [!NOTE]
> 서비스 어카운트 및 관련 POLICY 삭제
> ```
> eksctl delete iamserviceaccount --cluster=${CLUSTER_NAME} \
>  --namespace=rag --name=rag-mcp-sa
>
> export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
> export POLICY_ARN=arn:aws:iam::${ACCOUNT_ID}:policy/RAGMCPBedrockAccess
> aws iam delete-policy --policy-arn $POLICY_ARN
> ```

#### 4.2 Deployment & Service ####

`deployment.yaml`:
```bash
cat << 'EOF' > mcp-deployment.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: rag
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: rag-mcp
  namespace: rag
spec:
  replicas: 1
  selector:
    matchLabels:
      app: rag-mcp
  template:
    metadata:
      labels:
        app: rag-mcp
    spec:
      serviceAccountName: rag-mcp-sa
      containers:
        - name: rag-mcp
          image: ${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/rag-mcp:latest
          ports:
            - containerPort: 8000
          env:
            - name: MILVUS_HOST
              value: "milvus.milvus.svc.cluster.local"
            - name: MILVUS_PORT
              value: "19530"
            - name: MILVUS_COLLECTION
              value: "papers"
            - name: AWS_REGION
              value: "${AWS_REGION}"
            - name: BEDROCK_MODEL_ID
              value: "apac.anthropic.claude-3-5-sonnet-20241022-v2:0"
          resources:
            requests:
              cpu: "2"
              memory: "6Gi"
            limits:
              cpu: "4"
              memory: "8Gi"
          readinessProbe:
            httpGet:
              path: /sse
              port: 8000
            initialDelaySeconds: 60
            periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: rag-mcp
  namespace: rag
spec:
  type: ClusterIP
  selector:
    app: rag-mcp
  ports:
    - port: 80
      targetPort: 8000
EOF
```

```bash
envsubst < mcp-deployment.yaml | kubectl apply -f -
kubectl -n rag get pods -w
```

### 5. 테스트 ###

ClusterIP 상태이므로 port-forward로 터널을 연 뒤 MCP 클라이언트로 호출한다.

```bash
kubectl port-forward -n rag svc/rag-mcp 8000:80 &
PF_PID=$!
sleep 3
```

`test_client.py`:
```python
import asyncio
from mcp import ClientSession
from mcp.client.sse import sse_client

async def main():
    async with sse_client("http://localhost:8000/sse") as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("Tools:", [t.name for t in tools.tools])

            result = await session.call_tool(
                "search_papers",
                {"query": "LoRA가 뭐야?"},
            )
            print(result.content[0].text)

if __name__ == "__main__":
    asyncio.run(main())
```

```bash
python test_client.py
kill $PF_PID
```


### 리소스 요구량 ###
bge-m3 + bge-reranker-v2-m3 로딩에 메모리 약 5~6GB 필요.  

