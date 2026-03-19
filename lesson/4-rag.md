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

# 후보 모델들
models = {
    "bge-base": SentenceTransformer("BAAI/bge-base-en-v1.5"),
    "bge-large": SentenceTransformer("BAAI/bge-large-en-v1.5"),
    "e5-large": SentenceTransformer("intfloat/e5-large-v2"),
}

# 평가 데이터: (질문, 정답 문서) 쌍 30~50개 직접 작성
eval_data = [
    {"query": "GPU OOM 해결 방법은?", "relevant_doc_id": 0},
    {"query": "Slurm에서 멀티노드 학습 설정은?", "relevant_doc_id": 3},
    ...
]

# Hit Rate, MRR 측정
for name, model in models.items():
    hit = 0
    mrr = 0
    for item in eval_data:
        query_emb = model.encode(item["query"])
        # 벡터DB에서 상위 5개 검색 후 정답 문서가 포함되는지 확인
        results = search(query_emb, k=5)
        if item["relevant_doc_id"] in results:
            hit += 1
            rank = results.index(item["relevant_doc_id"]) + 1
            mrr += 1 / rank
    
    print(f"{name}: Hit Rate@5={hit/len(eval_data):.2f}, MRR@5={mrr/len(eval_data):.2f}")
```
* Hit Rate@5: 상위 5개 안에 정답이 포함된 비율
* MRR@5: 정답이 몇 번째에 있는지 (1위면 1.0, 2위면 0.5, 3위면 0.33)

### 3. 리랭커 모델 선정 ###





### 3. 아키텍처 설계 ###
아키텍처 설계는 이 파이프라인을 프로덕션에서 어떻게 운영할 것인가의 전체 그림이다.
- 인프라: FastAPI 서버, 벡터DB 클러스터, LLM 서빙(vLLM) 배치
- 확장성: 트래픽 증가 시 어떻게 스케일링할지
- 모니터링: Prometheus/Grafana로 검색 품질, 응답 시간 추적
- 캐싱: 반복 질문에 대한 응답 캐시
- 가드레일: 입력/출력 필터링, 환각 방지
- 비동기 평가: LLM Judge 백그라운드 실행
- 데이터 갱신: 새 문서 추가 시 인덱싱 파이프라인
