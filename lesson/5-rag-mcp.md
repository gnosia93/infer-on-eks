```
curl -o rag-mcp-server.py \
https://raw.githubusercontent.com/gnosia93/eks-agentic-ai/refs/heads/main/code/rag/rag-mcp-server.py
```

```
# 별도 터미널에서 Milvus port-forward 켜두기
kubectl port-forward -n milvus svc/milvus 19530:19530

# 다른 터미널
export AWS_REGION=ap-northeast-2
npx @modelcontextprotocol/inspector python rag_mcp_server.py
```
