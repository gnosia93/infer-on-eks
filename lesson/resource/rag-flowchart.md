flowchart TB
    subgraph Client
        User[사용자]
    end

    subgraph Gateway
        FastAPI[FastAPI Server]
        Cache[Response Cache]
        InputGuard[Input Guardrail]
    end

    subgraph Retrieval
        Embedding[Embedding Model]
        VectorDB[Vector DB - Hybrid Search]
        Reranker[Reranker - Cross-Encoder]
    end

    subgraph Generation
        vLLM[vLLM Server]
        OutputGuard[Output Guardrail - NLI]
    end

    subgraph Monitoring
        Prometheus[Prometheus]
        Grafana[Grafana Dashboard]
        Alert[AlertManager]
    end

    subgraph AsyncEval
        Logger[Request/Response Logger]
        Sampler[Sampling 10%]
        Judge[LLM-as-Judge]
    end

    subgraph DataPipeline
        Docs[새 문서 추가]
        Parser[Layout Parser]
        Chunker[Chunking]
        Indexer[Embedding + VectorDB 저장]
    end

    User -->|질문| FastAPI
    FastAPI --> Cache
    Cache -->|캐시 미스| InputGuard
    InputGuard --> Embedding
    Embedding --> VectorDB
    VectorDB --> Reranker
    Reranker --> vLLM
    vLLM --> OutputGuard
    OutputGuard --> FastAPI
    FastAPI -->|응답| User

    FastAPI -.-> Prometheus
    vLLM -.-> Prometheus
    Prometheus --> Grafana
    Prometheus --> Alert

    FastAPI -.-> Logger
    Logger --> Sampler
    Sampler --> Judge
    Judge -.-> Prometheus

    Docs --> Parser
    Parser --> Chunker
    Chunker --> Indexer
    Indexer --> VectorDB
