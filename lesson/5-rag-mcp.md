

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


