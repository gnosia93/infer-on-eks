
### 1. 파이프라인 ###
파이프라인 설계는 데이터가 흘러가는 순서와 각 단계의 기술에 대한 선택으로 어떤 청킹 전략을 쓸지, 임베딩 모델은 뭘 쓸지, 리랭커를 넣을지 말지와 같은 기술적 결정이다.

```
문서 수집 → (레이아웃) 파싱 → 청킹 → 임베딩 → 벡터DB 저장 → 검색 → 리랭킹 → LLM 생성
```

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
