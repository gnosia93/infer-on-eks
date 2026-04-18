## RAG 검색하기 (검색/리랭킹/LLM 답변) ##

앞 단계에서 Milvus에 저장한 벡터를 실제로 활용해 질의에 답변하는 단계다. 질의 하나가 들어오면 다음 세 단계를 순차로 거쳐 최종 답변이 만들어진다.
```
Query → Milvus 검색 (top 20) → bge-reranker-v2-m3 재정렬 (top 5) → Bedrock LLM 답변 생성
```
각 단계의 역할은 다음과 같다.

* Milvus 검색 : 질의를 벡터로 변환해 유사도가 높은 청크 20개를 빠르게 추려낸다. 속도는 빠르지만 정밀도는 다소 떨어진다.
* Reranker 재정렬 : CrossEncoder가 (질의, 청크) 쌍을 직접 비교해 점수를 매기고, 그중 가장 관련 깊은 5개만 남긴다. 느리지만 정확하다.
* LLM 답변 생성 : 선별된 컨텍스트를 근거로 Bedrock(Claude)이 최종 답변을 생성한다. 컨텍스트에 포함된 내용만 사용하도록 프롬프트로 제약해 환각(hallucination)을 줄인다.

아래 RAGSearch 클래스는 이 세 단계를 하나로 묶은 래퍼이다.

### 1. 프로젝트 구조 ###
```
rag/
├── PDFVectorStore.py   ← 저장용 클래스
├── RAGSearch.py        ← 검색용 클래스 (curl로 받음)
├── main.py             ← PDF 저장 스크립트
├── query.py            ← 검색 실행 스크립트
└── pdfs/
    └── LoRA_Low-Rank_Adaptation.pdf
```

### 2. 환경 준비 ###
Bedrock 호출에 필요한 boto3를 추가로 설치한다. 나머지 패키지(pymilvus, sentence-transformers 등)는 저장 단계에서 이미 설치돼 있다.
```
pip install boto3
```

### 3. RAGQuery 클래스 내려받기 ###
미리 작성해 둔 클래스 파일을 가져온다.
```
curl -o RAGSearch.py \
https://raw.githubusercontent.com/gnosia93/eks-agentic-ai/refs/heads/main/code/rag/RAGSearch.py
```
이 파일에는 다음 기능이 구현돼 있다. 
* 저장 때와 동일한 BAAI/bge-m3 모델로 질의 벡터화
* Milvus에서 유사도 기반 top-k 청크 검색
* BAAI/bge-reranker-v2-m3로 CrossEncoder 기반 재정렬
* Bedrock Converse API 호출로 Claude, Nova, Llama 등 모델을 동일한 인터페이스로 사용

### 4. 실행 스크립트 작성 (query.py) ###
```
import argparse
from RAGSearch import RAGSearch

def main():
    parser = argparse.ArgumentParser(description="Milvus + Bedrock RAG 질의 응답")
    parser.add_argument("--host", default="localhost", help="Milvus 호스트")
    parser.add_argument("--port", default="19530", help="Milvus 포트")
    parser.add_argument("--collection", default="papers", help="컬렉션 이름")
    parser.add_argument("--region", default="ap-northeast-2", help="AWS 리전")
    parser.add_argument(
        "--model",
        default="anthropic.claude-3-5-sonnet-20241022-v2:0",
        help="Bedrock 모델 ID",
    )
    parser.add_argument("--top-k", type=int, default=20, help="검색 후보 수")
    parser.add_argument("--top-n", type=int, default=5, help="재순위 후 사용할 수")
    parser.add_argument("query", help="질문")

    args = parser.parse_args()

    rag = RAGSearch(
        host=args.host,
        port=args.port,
        collection_name=args.collection,
        bedrock_model_id=args.model,
        aws_region=args.region,
    )

    result = rag.query(args.query, top_k=args.top_k, top_n=args.top_n)

    print("=" * 60)
    print(f"Q: {result['query']}")
    print("=" * 60)
    print(result["answer"])
    print("\n" + "-" * 60)
    print("참조한 컨텍스트:")
    for i, c in enumerate(result["contexts"], 1):
        print(f"  {i}. [{c['doc_name']} p.{c['page']}] "
              f"sim={c['score']:.3f} rerank={c['rerank_score']:.3f}")

if __name__ == "__main__":
    main()
```

### 5. 실행 ###
#### 5.1 Bedrock 모델 액세스 활성화 ####
AWS 콘솔에서 사용할 모델의 액세스를 먼저 열어줘야 한다.
```
AWS 콘솔 → Bedrock → Model access → 사용할 모델 "Request access"
```
리전마다 지원 모델이 다르다. Claude 계열은 us-west-2(Oregon)와 us-east-1(Virginia)에서 지원 폭이 가장 넓다.

#### 5.2 질의 실행 ####
Milvus가 EKS 내부(ClusterIP)에 있으므로 앞 단계와 동일하게 kubectl port-forward로 터널을 연 뒤 질의를 실행한다.
```
kubectl port-forward -n milvus svc/milvus 19530:19530 &
PF_PID=$!
sleep 3   # 포트 포워딩 준비 대기

export MILVUS_DB_IP=localhost

python query.py --host ${MILVUS_DB_IP} \
  "LoRA에서 low-rank adaptation이 왜 효과적인가?"

kill $PF_PID
```
실행이 끝나면 답변과 함께 근거로 사용된 문서/페이지가 함께 출력된다.
```
============================================================
Q: LoRA에서 low-rank adaptation이 왜 효과적인가?
============================================================
LoRA는 사전학습 모델의 가중치 업데이트(ΔW)가 실제로는 낮은 내재 차원을
가진다는 관찰에 기반합니다. ΔW = BA 형태로 저차원 행렬 두 개로 분해해
학습 파라미터를 크게 줄이면서도 풀 파인튜닝에 준하는 성능을 낸다.
...
참조: 02_LoRA_Low-Rank_Adaptation p.2, p.4
------------------------------------------------------------
참조한 컨텍스트:
  1. [02_LoRA_Low-Rank_Adaptation p.1] sim=0.812 rerank=0.934
  ...
```

