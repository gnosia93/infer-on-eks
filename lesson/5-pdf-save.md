## PDF 문서 저장하기 (레이아웃 파싱/청킹/임베딩) ##

이 단계에서는 PDF 문서를 읽어 들여 의미 단위로 잘게 나누고(청킹), 각 조각을 벡터로 변환해(임베딩) Milvus에 저장한다. 이렇게 저장된 벡터는 이후 RAG 파이프라인에서 질의와 가장 유사한 문서 조각을 찾는 데 사용된다.

전체 과정은 다음과 같다.
```
PDF 파일 → 레이아웃 파싱 → 청킹 → 임베딩(벡터화) → Milvus 저장
```
아래 PDFVectorStore 클래스는 이 네 단계를 하나로 묶어 둔 래퍼이다. 다른 PDF 문서도 같은 방식으로 추가할 수 있도록 재사용 가능한 형태로 작성돼 있다.

### 1. 프로젝트 구조 ### 
```
rag/
├── PDFVectorStore.py       ← curl로 받은 파일
└── main.py                 ← 여기서 from PDFVectorStore import ...
└── pdfs/
    └── LoRA_Low-Rank_Adaptation.pdf
```

### 2. 환경 준비 ###
작업 디렉토리를 만들고 필요한 패키지를 설치한다.

```
mkdir -p rag/pdfs && cd rag

pip install pymilvus langchain langchain-community pymupdf sentence-transformers
```
각 패키지의 역할: 
* pymilvus : Milvus 벡터 DB 파이썬 클라이언트
* langchain, langchain-community : 문서 로더와 텍스트 스플리터 제공
* pymupdf : PDF 레이아웃 파싱(텍스트/페이지 정보 추출)
* sentence-transformers : 로컬에서 실행되는 오픈소스 임베딩 모델 (무료)

### 3. PDFVectorStore 클래스 내려받기 ###
미리 작성해 둔 클래스 파일을 가져온다.
```
curl -o PDFVectorStore.py
https://raw.githubusercontent.com/gnosia93/eks-agentic-ai/refs/heads/main/code/rag/PDFVectorStore.py
```
이 파일 안에는 다음 기능이 구현돼 있다.  
* PyMuPDFLoader로 PDF를 페이지 단위로 로드
* RecursiveCharacterTextSplitter로 문맥을 최대한 보존하며 청킹 (기본 1,000자, 150자 오버랩)  
* BAAI/bge-m3 모델로 임베딩 (1,024차원, 다국어 지원)   
* Milvus 컬렉션 스키마 자동 생성 및 IVF_FLAT + COSINE 인덱스 구성

### 4. 실행 스크립트 작성 (main.py) ###
```
import argparse
from PDFVectorStore import PDFVectorStore

def main():
    parser = argparse.ArgumentParser(description="PDF 문서를 Milvus에 저장합니다.")
    parser.add_argument("--host", required=True, help="Milvus 호스트 (예: 10.0.0.5)")
    parser.add_argument("--port", default="19530", help="Milvus 포트 (기본값: 19530)")
    parser.add_argument("--collection", default="papers", help="컬렉션 이름 (기본값: papers)")
    parser.add_argument("--reset", action="store_true", help="기존 컬렉션 삭제 후 새로 생성")
    parser.add_argument("pdfs", nargs="+", help="저장할 PDF 파일 경로 (여러 개 가능)")

    args = parser.parse_args()

    store = PDFVectorStore(
        host=args.host,
        port=args.port,
        collection_name=args.collection,
        reset=args.reset,
    )

    for pdf_path in args.pdfs:
        store.add_pdf(pdf_path)

if __name__ == "__main__":
    main()
```

### 5. 실행 ###
pdf 를 다운로드 한다.
```
cat > download_pdfs.sh << 'EOF'
#!/bin/bash
mkdir -p pdfs

papers=(
  "01_Attention_Is_All_You_Need:1706.03762"
  "02_LoRA_Low-Rank_Adaptation:2106.09685"
  "03_RAG:2005.11401"
  "04_Chain_of_Thought:2201.11903"
  "05_ReAct:2210.03629"
  "06_FlashAttention:2205.14135"
  "07_Llama3_Technical_Report:2407.21783"
  "08_BGE_M3:2402.03216"
  "09_DeepSeek_R1:2501.12948"
  "10_Megatron_LM:1909.08053"
)

for paper in "${papers[@]}"; do
  name="${paper%%:*}"
  id="${paper##*:}"
  echo "Downloading $name ($id)..."
  curl -L -o "pdfs/${name}.pdf" "https://arxiv.org/pdf/${id}.pdf"
done

echo "Done!"
ls -lh pdfs/
EOF

sh download_pdfs.sh 
```
MILVUS_DB 에 pdf를 저장한다.
```
kubectl port-forward -n milvus svc/milvus 19530:19530 &
PF_PID=$!
sleep 3   # 포트 포워딩 준비 대기

export MILVUS_DB_IP=localhost
python main.py --host ${MILVUS_DB_IP} --reset pdfs/*.pdf

kill $PF_PID
```

