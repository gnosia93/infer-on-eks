## RAG ##

### 1. 파이프라인 ###

파이프라인 설계는 데이터가 흘러가는 순서와 각 단계의 기술에 대한 선택으로 어떤 청킹 전략을 쓸지, 임베딩 모델은 뭘 쓸지, 리랭커를 넣을지 말지와 같은 기술적 결정이다.
```
문서 수집 → (레이아웃) 파싱 → 청킹 → 임베딩 → 벡터DB 저장 → 검색 → 리랭킹 → LLM 생성
```

#### 저장 샘플 ####
```
from langchain_community.document_loaders import GitHubLoader, WebBaseLoader
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma

# 1. GitHub에서 마크다운 수집
loader = GitHubLoader(repo="aws/aws-parallelcluster", file_filter=lambda f: f.endswith(".md"))
docs = loader.load()

# 2. 청킹
from langchain.text_splitter import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
chunks = splitter.split_documents(docs)

# 3. 임베딩 + 벡터DB 저장
embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-base-en-v1.5")
vectordb = Chroma.from_documents(chunks, embeddings, persist_directory="./devops_vectordb")
```
* Chroma는 기본적으로 로컬 임베디드 DB로, SQLite처럼 별도 서버 없이 파일 기반으로 동작한다.


#### 검색 샘플 ####
```
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from sentence_transformers import CrossEncoder

# 벡터DB 로드
embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-base-en-v1.5")
vectordb = Chroma(persist_directory="./devops_vectordb", embedding_function=embeddings)

# 리랭커 로드
reranker = CrossEncoder("BAAI/bge-reranker-base")

# 1단계: 벡터 검색 (후보 10개)
query = "GPU OOM 해결 방법은?"
candidates = vectordb.similarity_search(query, k=10)

# 2단계: 리랭킹 (질문+문서 쌍을 크로스인코더로 점수 매김)
pairs = [[query, doc.page_content] for doc in candidates]
scores = reranker.predict(pairs)

# 3단계: 점수 순으로 정렬, 상위 3개 선택
ranked = sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)

for score, doc in ranked[:3]:
    print(f"[score: {score:.4f}]")
    print(doc.page_content[:200])
    print()
```

### 2. 임베딩 모델 선정 ###

#### 1단계: MTEB 리더보드에서 후보 선정 ####
[MTEB(Messaive Text Embedding Benchmark) Leaderboard](https://huggingface.co/spaces/mteb/leaderboard)에서 Retrieval 태스크 기준 상위 모델을 확인한다. 

![](https://github.com/gnosia93/agentic-ai-eks/blob/main/lesson/images/rag-embedding.png)

#### 2단계: 선정 기준 ####
* 언어: 한국어 포함이면 다국어 모델 필수 (bge-m3, Cohere Embed v3)
* 비용: API(Cohere, OpenAI) vs 오픈소스(self-hosted)
* 속도: 실시간 서비스면 작은 모델, 배치 처리면 큰 모델 가능
* 차원 수: 높을수록 정확하지만 벡터DB 저장 비용 증가
* 도메인: 기술 문서 위주면 영어 모델로 충분

#### 3단계: 도메인 데이터 평가 ###
MTEB 점수는 범용 벤치마크 기준이라, 실제 대상 도메인에서 성능이 다를 수 있으므로, 직접 평가하는 게 가장 정확하다.
```
from sentence_transformers import SentenceTransformer
import numpy as np

# 후보 모델
models = {
    "bge-base": SentenceTransformer("BAAI/bge-base-en-v1.5"),
    "bge-large": SentenceTransformer("BAAI/bge-large-en-v1.5"),
}

# 문서 데이터 (벡터DB에 들어갈 청크들)
documents = [
    "GPU OOM 해결: 배치 크기 줄이기, Gradient Accumulation, Mixed Precision, Activation Checkpointing 적용",
    "Kubernetes Pod CrashLoopBackOff: kubectl logs, kubectl describe pod로 이벤트 확인",
    "Prometheus는 pull 방식으로 메트릭 수집, PromQL로 시계열 데이터 쿼리",
    "Slurm 멀티노드 학습: sbatch에서 --nodes, --ntasks-per-node, --gpus-per-node 설정",
    "NCCL 통신 최적화: NCCL_DEBUG=INFO로 로그 확인, EFA 사용 시 FI_PROVIDER=efa 설정",
]

# 평가 데이터: (질문, 정답 문서 인덱스)
eval_data = [
    {"query": "GPU 메모리 부족할 때 어떻게 해?", "relevant_doc_id": 0},
    {"query": "Pod가 계속 재시작돼", "relevant_doc_id": 1},
    {"query": "Slurm에서 멀티노드 학습 설정은?", "relevant_doc_id": 3},
    {"query": "NCCL 성능 튜닝 방법은?", "relevant_doc_id": 4},
]

for name, model in models.items():
    doc_embs = model.encode(documents)  # 문서 임베딩
    hit = 0
    mrr = 0
    for item in eval_data:
        query_emb = model.encode(item["query"])
        scores = np.dot(doc_embs, query_emb)  # 코사인 유사도
        top_k = np.argsort(scores)[::-1][:5]   # 상위 5개 인덱스
        
        if item["relevant_doc_id"] in top_k:
            hit += 1
            rank = list(top_k).index(item["relevant_doc_id"]) + 1
            mrr += 1 / rank

    print(f"{name}: Hit Rate@5={hit/len(eval_data):.2f}, MRR@5={mrr/len(eval_data):.2f}")
```
* Hit Rate@5: 상위 5개 안에 정답이 포함된 비율
* MRR@5: 정답이 몇 번째에 있는지 (1위면 1.0, 2위면 0.5, 3위면 0.33)

> [!NOTE]
> 도메인 문서에 대해 질문과 정답 문서 쌍을 구성하고, 임베딩 모델별로 코사인 유사도(Cosine Similarity)를 계산하여 Top-N 검색 결과에 대한 Hit Rate와 MRR(Mean Reciprocal Rank)을 비교함으로써 최적의 임베딩 모델을 선정한다.



### 3. 리랭커 모델 선정 ###
임베딩 모델 선정 후, 벡터 검색으로 가져온 후보 문서들에 대해서 리랭커 적용 전후를 비교하여 리랭커가 실제로 검색 품질을 올려주는지도 확인해야 한다. 리랭커는 추론 비용과 지연 시간을 동반하므로, 사용하지 않을때와 비슷한 Hit Rate/MRR 보여주면 굳이 쓸 필요가 없다.

```
from sentence_transformers import CrossEncoder
import numpy as np

# 후보 리랭커
rerankers = {
    "bge-reranker-base": CrossEncoder("BAAI/bge-reranker-base"),
    "bge-reranker-large": CrossEncoder("BAAI/bge-reranker-large"),
    "ms-marco-mini": CrossEncoder("cross-encoder/ms-marco-MiniLM-L-12-v2"),
}

# 문서 데이터
documents = [
    "GPU OOM 해결: 배치 크기 줄이기, Gradient Accumulation, Mixed Precision, Activation Checkpointing 적용",
    "Kubernetes Pod CrashLoopBackOff: kubectl logs, kubectl describe pod로 이벤트 확인",
    "Prometheus는 pull 방식으로 메트릭 수집, PromQL로 시계열 데이터 쿼리",
    "Slurm 멀티노드 학습: sbatch에서 --nodes, --ntasks-per-node, --gpus-per-node 설정",
    "NCCL 통신 최적화: NCCL_DEBUG=INFO로 로그 확인, EFA 사용 시 FI_PROVIDER=efa 설정",
]

# 평가 데이터: 벡터 검색으로 후보 10개를 가져온 상태를 시뮬레이션
eval_data = [
    {"query": "GPU 메모리 부족할 때 어떻게 해?", "candidates": documents, "relevant_doc_id": 0},
    {"query": "Pod가 계속 재시작돼", "candidates": documents, "relevant_doc_id": 1},
    {"query": "Slurm에서 멀티노드 학습 설정은?", "candidates": documents, "relevant_doc_id": 3},
    {"query": "NCCL 성능 튜닝 방법은?", "candidates": documents, "relevant_doc_id": 4},
]

for name, reranker in rerankers.items():
    hit = 0
    mrr = 0
    for item in eval_data:
        pairs = [[item["query"], doc] for doc in item["candidates"]]
        scores = reranker.predict(pairs)
        top_k = np.argsort(scores)[::-1][:5]

        if item["relevant_doc_id"] in top_k:
            hit += 1
            rank = list(top_k).index(item["relevant_doc_id"]) + 1
            mrr += 1 / rank

    print(f"{name}: Hit Rate@5={hit/len(eval_data):.2f}, MRR@5={mrr/len(eval_data):.2f}")
```

> [!NOTE]
> 리랭커는 벡터 검색이 가져온 후보 문서들을 질문과 함께 다시 읽고, 관련성 순서를 재정렬하는 모델이다.
벡터 검색(Bi-Encoder)은 질문과 문서를 각각 따로 임베딩해서 유사도를 비교하기 때문에 빠르지만, 질문과 문서 사이의 세밀한 의미 관계를 놓칠 수 있다.
리랭커(Cross-Encoder)는 인코더 트랜스포머(BERT 계열)로, 질문과 후보 문서를 하나의 시퀀스로 결합한 뒤 Self-Attention을 통해 질문의 모든 토큰과 후보 문서의 모든 토큰 간 상호 관계를 계산하여 관련성 점수를 산출한다.
> ```
> 1단계: 벡터 검색 → 수만 건에서 후보 10~20개를 빠르게 추림 (Bi-Encoder, 빠름)
> 2단계: 리랭커 → 후보 10~20개를 정밀하게 재정렬 (Cross-Encoder, 정확)
> ```

### 4. 벡터DB 선정기준 ###
* 하이브리드 검색 지원 여부
* 확장성
  * 데이터 규모: 수만 건이면 뭘 써도 되지만, 수천만~억 건이면 Milvus, Pinecone처럼 분산 아키텍처가 필요
  * 동시 요청: 트래픽이 많으면 수평 확장(샤딩, 레플리카) 지원 여부 확인
* 메타데이터 필터링 - 검색 시 벡터 유사도 + 메타데이터 조건을 함께 걸 수 있는지.

### 5. 아키텍처 설계 ###
아키텍처 설계는 이 파이프라인을 프로덕션에서 어떻게 운영할 것인가의 전체 그림이다.
- 인프라: FastAPI 서버, 벡터DB 클러스터, LLM 서빙(vLLM) 배치
- 확장성: 트래픽 증가 시 어떻게 스케일링할지
- 모니터링: Prometheus/Grafana로 검색 품질, 응답 시간 추적
- 캐싱: 반복 질문에 대한 응답 캐시
- 가드레일: 입력/출력 필터링, 환각 방지
- 비동기 평가: LLM Judge 백그라운드 실행
- 데이터 갱신: 새 문서 추가 시 인덱싱 파이프라인
