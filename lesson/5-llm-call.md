<< 작성중 >> 

전체 과정은 다음과 같다.
```
Query → Milvus 검색 (top 20) → Cohere Rerank (top 5) → Bedrock LLM
```

### 1. 프로젝트 구조 ###
```
rag/
├── PDFVectorStore.py   
├── RAGQuery.py         ← curl로 받은 파일
├── main.py             
└── pdfs/               
    └── LoRA_Low-Rank_Adaptation.pdf
```

설치
```
curl -o RAGSearch.py \
https://raw.githubusercontent.com/gnosia93/eks-agentic-ai/refs/heads/main/code/rag/RAGSearch.py

```

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
