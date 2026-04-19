# Neo4j로 지식 그래프 구현하기

## 온톨로지(Ontology)란?

온톨로지는 원래 "존재하는 것은 무엇인가"를 다루는 철학 용어지만, 컴퓨터 과학에서는 **특정 도메인의 개념·속성·관계를 기계가 이해할 수 있는 형태로 정의한 지식 체계**를 뜻한다.

예를 들어 단순한 JSON 데이터 `{"name": "홍길동", "company": "Cohere"}` 만 보면 컴퓨터는 "홍길동"이 사람인지 회사인지 알 수 없다. 반면 온톨로지는 *"Person은 name을 가지며, Organization에 worksFor 관계로 연결된다"* 처럼 의미와 관계를 명시해, 기계가 데이터를 추론할 수 있게 만든다.

이 구조를 실제 데이터로 실체화한 것이 **지식 그래프(Knowledge Graph)** 이며, Neo4j 같은 그래프 DB로 구현한다. 최근에는 LLM과 결합한 **GraphRAG** 로 확장되어, 벡터 기반 RAG가 약한 "관계 기반 추론"을 보완하는 기술로 주목받고 있다.

---

## Neo4j 설치

### 1. Helm 저장소 추가

```bash
helm repo add neo4j https://helm.neo4j.com/neo4j
helm repo update
```

### 2. values 파일 작성

`neo4j-values.yaml` 파일을 생성한다.

```bash
cat <<'EOF' > neo4j-values.yaml
neo4j:
  name: neo4j
  edition: community            # 무료 버전
  password: "neo4j-admin"       # 초기 비밀번호 (8자 이상 필수)

  resources:
    cpu: "1"
    memory: "4Gi"

volumes:
  data:
    mode: defaultStorageClass
    defaultStorageClass:
      requests:
        storage: 20Gi

services:
  neo4j:
    enabled: true
    type: ClusterIP             # 클러스터 내부 접근만 허용

# Graviton(ARM) 노드에 스케줄링
nodeSelector:
  kubernetes.io/arch: arm64
EOF
```

### 3. 설치

```bash
helm install neo4j neo4j/neo4j -n neo4j \
  -f neo4j-values.yaml --create-namespace
```

### 4. 설치 확인

```bash
kubectl get all -n neo4j
```

`neo4j-0` Pod가 Running 상태가 될 때까지 1~2분 정도 걸린다 (PVC 바인딩 + Neo4j 초기화 과정).

---

## 접속 테스트

Neo4j가 ClusterIP로 떠 있으므로 Milvus와 동일하게 `kubectl port-forward`로 터널을 연 뒤 접속한다.

```bash
pip install neo4j

kubectl port-forward -n neo4j svc/neo4j 7474:7474 7687:7687 &
PF_PID=$!
sleep 3
```

`test.py` 작성:

```python
from neo4j import GraphDatabase

driver = GraphDatabase.driver(
    "bolt://localhost:7687",
    auth=("neo4j", "neo4j-admin"),     # values.yaml에서 설정한 비밀번호
)

with driver.session() as session:
    # 테스트 데이터 생성
    session.run("""
        CREATE (p:Paper {title: 'LoRA', year: 2021})
        CREATE (a:Author {name: 'Edward Hu'})
        CREATE (a)-[:AUTHORED]->(p)
    """)

    # 쿼리
    result = session.run("""
        MATCH (a:Author)-[:AUTHORED]->(p:Paper)
        RETURN a.name AS author, p.title AS title
    """)
    for r in result:
        print(f"{r['author']} → {r['title']}")

driver.close()
```

실행:

```bash
python test.py
# Edward Hu → LoRA

kill $PF_PID
```

---

## 브라우저 UI로 확인 (선택)

Neo4j Browser에서 그래프를 시각적으로 확인할 수 있다.

`http://localhost:7474` 접속 후 입력:

- Connect URL: `bolt://localhost:7687`
- Username: `neo4j`
- Password: `neo4j-admin`

로그인하면 방금 Python으로 생성한 `Author → Paper` 관계를 그래프 형태로 탐색할 수 있다.

```cypher
MATCH (a:Author)-[:AUTHORED]->(p:Paper)
RETURN a, p
```

> [!NOTE]
> 운영 환경에서는 기본 비밀번호를 반드시 변경하고, 외부 노출 시 ALB + ACM으로 HTTPS를 적용해야 한다.

---

## 정리

```bash
# port-forward 종료
kill $PF_PID

# Neo4j 제거 (필요시)
helm uninstall neo4j -n neo4j

# 데이터까지 완전 삭제 (PVC)
kubectl delete pvc -n neo4j --all
```
