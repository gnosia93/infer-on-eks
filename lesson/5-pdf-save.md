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
├── PDFVectorStore.py   ← curl로 받은 파일
├── main.py             ← 실행 스크립트
└── pdfs/               ← PDF 파일 보관
    └── LoRA_Low-Rank_Adaptation.pdf
```

### 2. 환경 준비 ###
작업 디렉토리를 만들고 필요한 패키지를 설치한다.

```
mkdir -p rag/pdfs && cd rag

pip install pymilvus langchain langchain-community pymupdf sentence-transformers
pip install langchain-text-splitters
```
각 패키지의 역할: 
* pymilvus : Milvus 벡터 DB 파이썬 클라이언트
* langchain, langchain-community : 문서 로더와 텍스트 스플리터 제공
* pymupdf : PDF 레이아웃 파싱(텍스트/페이지 정보 추출)
* sentence-transformers : 로컬에서 실행되는 오픈소스 임베딩 모델 (무료)

### [3. PDFVectorStore 클래스 내려받기](https://github.com/gnosia93/eks-agentic-ai/blob/main/code/rag/PDFVectorStore.py) ###
미리 작성해 둔 클래스 파일을 가져온다.
```
curl -o PDFVectorStore.py \
https://raw.githubusercontent.com/gnosia93/eks-agentic-ai/refs/heads/main/code/rag/PDFVectorStore.py
```
이 파일 안에는 다음 기능이 구현돼 있다.  
* PyMuPDFLoader로 PDF를 페이지 단위로 로드
* RecursiveCharacterTextSplitter로 문맥을 최대한 보존하며 청킹 (기본 1,000자, 150자 오버랩)  
* BAAI/bge-m3 모델로 임베딩 (1,024차원, 다국어 지원)   
* Milvus 컬렉션 스키마 자동 생성 및 IVF_FLAT + COSINE 인덱스 구성

### 4. 실행 스크립트 작성 (main.py) ###
```
cat << 'EOF' > main.py
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
EOF
```

### 5. 실행 ###

#### 5.1 PDF 다운로드 ####
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
```
pdf 문서를 다운로드 한다.
```
bash download_pdfs.sh 
```

#### 5.2 MILVUS에 저장 ####
EKS에서 Milvus는 `ClusterIP`로 떠 있어 외부에서 직접 접근할 수 없으므로, `kubectl port-forward`로 로컬 포트에 터널링한 뒤 접속한다.
최초 실행 시 `BAAI/bge-m3` 임베딩 모델(약 2.3GB)이 자동 다운로드되므로 수 분 소요될 수 있다.

```
kubectl port-forward -n milvus svc/milvus 19530:19530 &
PF_PID=$!
sleep 3   # 포트 포워딩 준비 대기

export MILVUS_DB_IP=localhost
python main.py --host ${MILVUS_DB_IP} --reset pdfs/*.pdf
```
[결과]
```
Handling connection for 19530
I0419 03:37:26.800686   39780 fork_posix.cc:71] Other threads are currently calling into gRPC, skipping fork() handlers
I0419 03:37:26.831408   39780 fork_posix.cc:71] Other threads are currently calling into gRPC, skipping fork() handlers
I0419 03:37:26.854061   39780 fork_posix.cc:71] Other threads are currently calling into gRPC, skipping fork() handlers
I0419 03:37:26.874887   39780 fork_posix.cc:71] Other threads are currently calling into gRPC, skipping fork() handlers
modules.json: 100%|██████████████████████████████████████████████████████████████████████████████████| 349/349 [00:00<00:00, 1.94MB/s]
config_sentence_transformers.json: 100%|█████████████████████████████████████████████████████████████| 123/123 [00:00<00:00, 1.19MB/s]
README.md: 15.8kB [00:00, 47.2MB/s]
sentence_bert_config.json: 100%|████████████████████████████████████████████████████████████████████| 54.0/54.0 [00:00<00:00, 561kB/s]
config.json: 100%|███████████████████████████████████████████████████████████████████████████████████| 687/687 [00:00<00:00, 5.26MB/s]
Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable higher rate limits and faster downloads.
pytorch_model.bin: 100%|██████████████████████████████████████████████████████████████████████████| 2.27G/2.27G [00:18<00:00, 122MB/s]
Loading weights: 100%|███████████████████████████████████████████████████████████████████████████| 391/391 [00:00<00:00, 32958.98it/s]
tokenizer_config.json: 100%|█████████████████████████████████████████████████████████████████████████| 444/444 [00:00<00:00, 4.02MB/s]
sentencepiece.bpe.model: 100%|███████████████████████████████████████████████████████████████████| 5.07M/5.07M [00:00<00:00, 12.4MB/s]
tokenizer.json: 100%|████████████████████████████████████████████████████████████████████████████| 17.1M/17.1M [00:00<00:00, 41.8MB/s]
special_tokens_map.json: 100%|███████████████████████████████████████████████████████████████████████| 964/964 [00:00<00:00, 4.58MB/s]
config.json: 100%|███████████████████████████████████████████████████████████████████████████████████| 191/191 [00:00<00:00, 1.76MB/s]
model.safetensors: 100%|██████████████████████████████████████████████████████████████████████████| 2.27G/2.27G [00:18<00:00, 122MB/s]
[01_Attention_Is_All_You_Need] inserted 49 chunks
[02_LoRA_Low-Rank_Adaptation] inserted 104 chunks
[03_RAG] inserted 88 chunks
[04_Chain_of_Thought] inserted 173 chunks
[05_ReAct] inserted 140 chunks
[06_FlashAttention] inserted 139 chunks
[07_Llama3_Technical_Report] inserted 451 chunks
[08_BGE_M3] inserted 87 chunks
[09_DeepSeek_R1] inserted 297 chunks
[10_Megatron_LM] inserted 84 chunks
```

## Sanity Check ##
```bash
curl -o check_milvus.py \
https://raw.githubusercontent.com/gnosia93/eks-agentic-ai/refs/heads/main/code/rag/check_milvus.py

python check_milvus.py
```
[결과]
```
Handling connection for 19530
✅ Collection: papers
   총 청크 수: 1612

스키마:
   - id (INT64)
   - embedding (FLOAT_VECTOR)
   - text (VARCHAR)
   - doc_name (VARCHAR)
   - source (VARCHAR)
   - page (INT64)

문서별 청크 분포:
   01_Attention_Is_All_You_Need: 49 chunks
   02_LoRA_Low-Rank_Adaptation: 104 chunks
   03_RAG: 88 chunks
   04_Chain_of_Thought: 173 chunks
   05_ReAct: 140 chunks
   06_FlashAttention: 139 chunks
   07_Llama3_Technical_Report: 451 chunks
   08_BGE_M3: 87 chunks
   09_DeepSeek_R1: 297 chunks
   10_Megatron_LM: 84 chunks
```

```bash
curl -o test_search.py \
https://raw.githubusercontent.com/gnosia93/eks-agentic-ai/refs/heads/main/code/rag/test_search.py

python test_search.py
```
[결과]
```
Handling connection for 19530
I0419 03:59:26.106296   53106 fork_posix.cc:71] Other threads are currently calling into gRPC, skipping fork() handlers
I0419 03:59:26.139304   53106 fork_posix.cc:71] Other threads are currently calling into gRPC, skipping fork() handlers
I0419 03:59:26.173574   53106 fork_posix.cc:71] Other threads are currently calling into gRPC, skipping fork() handlers
I0419 03:59:26.204646   53106 fork_posix.cc:71] Other threads are currently calling into gRPC, skipping fork() handlers
Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable higher rate limits and faster downloads.
Loading weights: 100%|███████████████████████████████████████████████████████████████████████████| 391/391 [00:00<00:00, 54019.33it/s]

질의: What is LoRA?
======================================================================

1. [02_LoRA_Low-Rank_Adaptation p.0] score=0.533
   LORA: LOW-RANK ADAPTATION OF LARGE LAN-
GUAGE MODELS
Edward Hu∗
Yelong Shen∗
Phillip Wallis
Zeyuan Allen-Zhu
Yuanzhi Li
Shean Wang
Lu Wang
Weizhu Chen
Microsoft Corporation
{edwardhu, yeshe, phwallis,...

2. [02_LoRA_Low-Rank_Adaptation p.4] score=0.506
   on the ﬂy on machines that store the pre-trained weights in VRAM. We also observe a 25% speedup
during training on GPT-3 175B compared to full ﬁne-tuning5 as we do not need to calculate the
gradient f...

3. [02_LoRA_Low-Rank_Adaptation p.0] score=0.501
   layer of the Transformer architecture, greatly reducing the number of trainable pa-
rameters for downstream tasks. Compared to GPT-3 175B ﬁne-tuned with Adam,
LoRA can reduce the number of trainable p...

...
```

포트 포워딩을 종료한다. 
```
kill $PF_PID
```
[결과]
```
[1]+  Terminated              kubectl port-forward -n milvus svc/milvus 19530:19530
```

## 참고 - [BAAI/bge-m3](https://arxiv.org/pdf/2402.03216) ##
BAAI(베이징 지능연구원)가 2024년 공개한 오픈소스 다국어 임베딩 모델. 이름의 "M3"는 세 가지 M을 뜻한다.

* Multi-Linguality : 한국어 포함 100+ 언어
* Multi-Functionality : dense / sparse / multi-vector 검색을 한 모델로
* Multi-Granularity : 최대 8,192 토큰까지 처리

주요 스펙:

* 베이스	XLM-RoBERTa-large
* 임베딩 차원	1,024
* 최대 입력	8,192 토큰
* 모델 크기	약 2.3GB
* 라이선스	MIT

강점:

* 한국어/다국어 검색 품질이 우수 (한글 질의 ↔ 영어 문서 크로스링궐도 잘됨)
* 긴 문서 처리 가능 (대부분 모델은 512 토큰)
* 무료, 로컬 실행 가능
* 본 워크샵처럼 영어 논문을 한국어로 검색하는 RAG 파이프라인에 잘 맞는 선택.

허깅페이스 :  

* https://huggingface.co/BAAI/bge-m3
