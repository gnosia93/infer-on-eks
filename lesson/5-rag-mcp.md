

* https://github.com/gnosia93/eks-agentic-ai/blob/main/code/rag/rag-mcp-server.py
```
curl -o rag-mcp-server.py \
https://raw.githubusercontent.com/gnosia93/eks-agentic-ai/refs/heads/main/code/rag/rag-mcp-server.py
```
* MILVUS_HOST의 기본값이 milvus.milvus.svc.cluster.local. 같은 클러스터 내부에선 이 이름으로 바로 접근 가능.



### 2. Docker 이미지 만들기 ###
* requirements.txt
```
mcp>=1.0.0
pymilvus>=2.4.0
sentence-transformers>=3.0.0
langchain
langchain-community
pymupdf
boto3
```
* Dockerfile
```
FROM python:3.11-slim

WORKDIR /app

# 시스템 의존성 (torch가 필요로 하는 것들)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 파이썬 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 모델 사전 다운로드 (이미지 빌드 시점에 받아두면 Pod 시작 빠름)
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; \
    SentenceTransformer('BAAI/bge-m3'); \
    CrossEncoder('BAAI/bge-reranker-v2-m3')"

# 앱 코드
COPY RAGSearch.py rag_mcp_server.py ./
EXPOSE 8000
CMD ["python", "rag_mcp_server.py"]
```

### 3. 빌드 / ecr 푸시 ### 
```
# ECR 리포지토리 생성 (최초 한 번)
aws ecr create-repository --repository-name rag-mcp --region us-west-2

# 로그인
aws ecr get-login-password --region us-west-2 | \
  docker login --username AWS --password-stdin \
  <ACCOUNT_ID>.dkr.ecr.us-west-2.amazonaws.com

# 빌드 & 푸시
docker build -t rag-mcp:latest .
docker tag rag-mcp:latest <ACCOUNT_ID>.dkr.ecr.us-west-2.amazonaws.com/rag-mcp:latest
docker push <ACCOUNT_ID>.dkr.ecr.us-west-2.amazonaws.com/rag-mcp:latest
```
* 이미지 사이즈가 꽤 크다(모델 2개가 약 4GB). 프로덕션이면 모델을 초기화 때 다운로드하거나 PVC로 분리하는 것도 방법.


### 4. eks 배포 ###
#### EKS 배포 (Bedrock 호출용 IRSA 포함) ####
iam-policy.json (Bedrock 호출 권한):
```
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["bedrock:InvokeModel", "bedrock:Converse"],
    "Resource": "*"
  }]
}
```

#### IRSA 설정 ####
```
# IAM 정책 생성
aws iam create-policy \
  --policy-name RAGMCPBedrockAccess \
  --policy-document file://iam-policy.json

# eksctl로 ServiceAccount + IAM Role 연결
eksctl create iamserviceaccount \
  --cluster=<클러스터명> \
  --namespace=rag \
  --name=rag-mcp-sa \
  --attach-policy-arn=arn:aws:iam::<ACCOUNT_ID>:policy/RAGMCPBedrockAccess \
  --approve
```
deployment
```
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
      serviceAccountName: rag-mcp-sa   # IRSA
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
            initialDelaySeconds: 60   # 모델 로딩 시간
            periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: rag-mcp
  namespace: rag
spec:
  type: ClusterIP   # 우선 내부용
  selector:
    app: rag-mcp
  ports:
    - port: 80
      targetPort: 8000
```
* kubectl apply -f deployment.yaml
* kubectl -n rag get pods -w

## 테스트 ##
포트 포워딩 설정 후 테스트..
```
from mcp import ClientSession
from mcp.client.sse import sse_client

async with sse_client("https://rag-mcp.yourdomain.com/sse") as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool(
            "search_papers",
            {"query": "LoRA가 뭐야?"}
        )
        print(result)
```

## 운영 포인트 ##
```
꼭 챙겨야 할 운영 포인트
인증 (외부 공개 시 필수)

MCP 자체엔 인증이 없어요. 보통 앞단에 다음 중 하나를 둡니다:

ALB 레벨: Cognito, OIDC 통합
API 키: Nginx/ALB 앞에 간단한 API Gateway
IAM 인증 ALB: SigV4로 서명된 요청만 허용
VPN/PrivateLink: 특정 VPC에서만 접근
리소스 요구량

bge-m3 + bge-reranker-v2-m3 로딩 시 메모리 약 56GB 필요. CPU로만 돌리면 응답 13초, GPU 노드 쓰면 훨씬 빠름.

스케일링

MCP SSE는 stateful 연결이라 HPA 적용 시 sticky session 고려
동시 사용자 많으면 replicas 늘리고 LB에서 분배
모델 로딩이 무거우니 스케일 아웃보단 스케일 업이 효율적일 수도
Milvus 컬렉션 로드

Collection.load()가 __init__에 있어서 서버 시작 시 Milvus에도 로드 요청이 감. Milvus 쪽 메모리도 감안.
```
