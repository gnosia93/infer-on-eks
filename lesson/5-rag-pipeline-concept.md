
### 1. 파이프라인 ###
파이프라인 설계는 데이터가 흘러가는 순서와 각 단계의 기술에 대한 선택으로 어떤 청킹 전략을 쓸지, 임베딩 모델은 뭘 쓸지, 리랭커를 넣을지 말지와 같은 기술적 결정이다.

![](https://github.com/gnosia93/eks-agentic-ai/blob/main/lesson/images/rag-pipeline.png)
* 문서 수집 → (레이아웃) 파싱 → 청킹 → 임베딩 → 벡터DB 저장 → 검색 → 리랭킹 → LLM 생성

### 2. 청킹 전략 ###

```
1. Fixed Size Chunking       — 정해진 크기로 기계적 분할
2. Recursive Chunking        — 구분자 우선순위로 재귀 분할
3. Document-Aware Chunking   — 문서 구조(제목/섹션) 기반 분할
4. Semantic Chunking         — 의미 유사도 기반 분할
5. Sliding Window            — 중첩(overlap) 두고 분할
6. Parent-Child Chunking     — 작게 검색, 크게 답변
7. Agentic Chunking          — LLM이 직접 나눔
```

### 3. 임베딩 모델 선정 ###

#### 1. 성능 (벤치마크) ####
* MTEB (Massive Text Embedding Benchmark) — 영어 표준
* https://huggingface.co/spaces/mteb/leaderboard
* MTEB Korean / KoMTEB — 한국어 평가
* BEIR — 검색 특화 벤치마크

[벤치마크 해석]
```
* Retrieval 점수가 RAG에선 제일 중요 (분류/클러스터링 점수 아님)
* 전체 평균만 보지 말고 내 도메인과 비슷한 태스크 점수 확인
* 주의: 벤치마크 성능 1~2% 차이는 실제 체감 거의 없음. 상위권 모델 중에 다른 요소(비용, 차원)로 고르는 게 현실적.
```

#### 2. 차원 수 (중요!) ####
벡터 차원이 크면 정확도↑, 저장/검색 비용↑.

#### 3. 최대 토큰 (context length) ####
* 한 번에 임베딩할 수 있는 최대 길이(청크 사이즈) 
* 긴 문서 다루면 8K 지원 모델 유리. 짧은 청크(300~500)만 쓸 거면 512로도 충분.

#### 4. 비용 모델 ####
* API 기반:
```
OpenAI text-embedding-3-small: $0.02 / 1M tokens
OpenAI text-embedding-3-large: $0.13 / 1M tokens
Cohere embed-v3:              $0.10 / 1M tokens
Voyage AI:                    $0.12 / 1M tokens
```
* 자체 호스팅 (오픈소스):
```
서버 비용 (GPU 인스턴스)
BGE-M3, E5 등은 무료
```

#### 5. 도메인 적합성 ####
일반 모델은 범용적이지만, 특수 도메인이면 전용 모델이 나음
```
코드: voyage-code-2, jina-embeddings-v2-code, CodeBERT
의료: BioBERT, PubMedBERT 기반
법률: LegalBERT
금융: FinBERT
```
다만 대부분은 범용 + 리랭커 조합이 실용적. 도메인 모델은 학습 데이터가 제한적이라 일반 질문엔 약할 수 있음.


### 4. 벡터DB 선정기준 ###
* 하이브리드 검색 지원 여부
* 확장성
  * 데이터 규모: 수만 건이면 뭘 써도 되지만, 수천만~억 건이면 Milvus, Pinecone처럼 분산 아키텍처가 필요
  * 동시 요청: 트래픽이 많으면 수평 확장(샤딩, 레플리카) 지원 여부 확인
* 메타데이터 필터링 - 검색 시 벡터 유사도 + 메타데이터 조건을 함께 걸 수 있는지.


### 5. 리랭커 모델 선정 ###
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
> [!Tip]
>
> 리랭커는 벡터 검색이 가져온 후보 문서들을 질문과 함께 다시 읽고, 관련성 순서를 재정렬하는 모델이다. 벡터 검색(Bi-Encoder)은 질문과 문서를 각각 따로 임베딩해서 유사도를 비교하기 때문에 빠르지만, 질문과 문서 사이의 세밀한 의미 관계를 놓칠 수 있다. 리랭커(Cross-Encoder)는 인코더 트랜스포머(BERT 계열)로, 질문과 후보 문서를 하나의 시퀀스로 결합한 뒤 Self-Attention을 통해 질문의 모든 토큰과 후보 문서의 모든 토큰 간 상호 관계를 계산하여 관련성 점수를 산출한다.
> 
> 1단계: 벡터 검색 → 수만 건에서 후보 10 ~ 20개를 빠르게 추림 (Bi-Encoder, 빠름)   
> 2단계: 리랭커 → 후보 10 ~ 20개를 정밀하게 재정렬 (Cross-Encoder, 정확)

