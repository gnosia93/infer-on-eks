## RAGSearch MCP 서버 배포 (EKS) ##

RAGSearch를 MCP 서버로 감싸 EKS에 Pod로 배포한다. 외부 에이전트는 MCP 클라이언트로 Tool을 호출해 논문 검색 및 답변 생성을 원격으로 사용할 수 있다.

```
외부 에이전트 (MCP Client)
        │  HTTP/SSE
        ▼
┌─────────────── EKS ───────────────┐
│   rag-mcp Pod (FastMCP + SSE)     │
│        │                          │
│        ▼                          │
│   Milvus (ClusterIP)              │
└───────────────────────────────────┘
        │
        ▼ (VPC 외부)
      AWS Bedrock
```

### [1. rag_mcp_server.py 내려받기](https://github.com/gnosia93/eks-agentic-ai/blob/main/code/rag/rag-mcp-server.py) ###

```bash
curl -o rag_mcp_server.py \
https://raw.githubusercontent.com/gnosia93/eks-agentic-ai/refs/heads/main/code/rag/rag-mcp-server.py
```

`MILVUS_HOST` 기본값은 `milvus.milvus.svc.cluster.local`로, 같은 클러스터 내부에서 Milvus에 바로 접근한다.
```
kubectl get svc -n milvus
```
[결과]
```
NAME                   TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)              AGE
milvus                 ClusterIP   172.20.101.0    <none>        19530/TCP,9091/TCP   9h
milvus-etcd            ClusterIP   172.20.213.13   <none>        2379/TCP,2380/TCP    9h
milvus-etcd-headless   ClusterIP   None            <none>        2379/TCP,2380/TCP    9h
```

> [!NOTE]
> 쿠버네티스(Kubernetes) 내부 DNS 형식  
> `<service-name>.<namespace>.svc.cluster.local`


### 2. Docker 이미지 빌드 ###

`requirements.txt`:
```
mcp>=1.0.0
pymilvus>=2.4.0
sentence-transformers>=3.0.0
langchain
langchain-community
pymupdf
boto3
```

`Dockerfile`:
```dockerfile
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
```

> 이미지 크기가 크다(모델 2개 약 4GB). 프로덕션에서는 PVC로 모델을 분리하는 방법도 있다.

### 3. ECR 푸시 ###

```bash
aws ecr create-repository --repository-name rag-mcp --region us-west-2

aws ecr get-login-password --region us-west-2 | \
  docker login --username AWS --password-stdin \
  <ACCOUNT_ID>.dkr.ecr.us-west-2.amazonaws.com

docker build -t rag-mcp:latest .
docker tag rag-mcp:latest <ACCOUNT_ID>.dkr.ecr.us-west-2.amazonaws.com/rag-mcp:latest
docker push <ACCOUNT_ID>.dkr.ecr.us-west-2.amazonaws.com/rag-mcp:latest
```

### 4. EKS 배포 ###

#### 4.1 Bedrock 접근 권한 (IRSA) ####

`iam-policy.json`:
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["bedrock:InvokeModel", "bedrock:Converse"],
    "Resource": "*"
  }]
}
```

```bash
aws iam create-policy \
  --policy-name RAGMCPBedrockAccess \
  --policy-document file://iam-policy.json

eksctl create iamserviceaccount \
  --cluster=<클러스터명> \
  --namespace=rag \
  --name=rag-mcp-sa \
  --attach-policy-arn=arn:aws:iam::<ACCOUNT_ID>:policy/RAGMCPBedrockAccess \
  --approve
```

#### 4.2 Deployment & Service ####

`deployment.yaml`:
```yaml
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
          image: <ACCOUNT_ID>.dkr.ecr.us-west-2.amazonaws.com/rag-mcp:latest
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
              value: "us-west-2"
            - name: BEDROCK_MODEL_ID
              value: "anthropic.claude-3-5-sonnet-20241022-v2:0"
          resources:
            requests:
              cpu: "1"
              memory: "6Gi"
            limits:
              cpu: "2"
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
```

```bash
kubectl apply -f deployment.yaml
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

### 운영 포인트 ###

**인증 (외부 공개 시 필수)**
MCP 프로토콜 자체에는 인증이 없어 앞단에 인증 계층을 둬야 한다.
- ALB + Cognito/OIDC
- API Gateway + API 키
- IAM 인증 ALB (SigV4)
- VPN/PrivateLink로 내부 접근만 허용

**리소스 요구량**
bge-m3 + bge-reranker-v2-m3 로딩에 메모리 약 5~6GB 필요. CPU만 쓰면 질의 응답에 1~3초, GPU 노드면 훨씬 빠르다.

**스케일링**
SSE는 stateful 연결이라 HPA 적용 시 sticky session 설정이 필요하다. 모델 로딩이 무거워 스케일 아웃보다 스케일 업이 효율적인 경우가 많다.

**Milvus 컬렉션 로드**
`Collection.load()`가 생성자에 있어 서버 시작 시 Milvus도 메모리에 올린다. Milvus 쪽 메모리 할당도 함께 고려한다.
