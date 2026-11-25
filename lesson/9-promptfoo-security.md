promptfoo 레드팀 스캔은 공격 프롬프트를 자동으로 만들어 대상 엔드포인트에 보내고, 채점 모델이 응답의 정책 위반 여부를 판정하는 방식이다. 플러그인은 공격 주제(유해 콘텐츠, 개인정보, 시스템 프롬프트 유출 등)를 정하고, 전략은 공격을 감싸는 방식(탈옥, 인코딩, 멀티턴)을 정한다. 아래 절차는 이 레포 구성인 LiteLLM → vLLM gemma-4-12b에 맞췄다.

### 1. 준비 ###
최신 promptfoo(0.126.0)는 Node.js 22.22.0 이상이 필요하다. 

```
mkdir -p ~/promptfoo-redteam && cd ~/promptfoo-redteam
mise use node@24      # 이 디렉터리에서만 Node 24 사용

# ALB가 internal이라 로컬에서는 LiteLLM으로 포트 포워딩
kubectl -n llm-serving port-forward svc/litellm 4000:4000 >/dev/null 2>&1 &
export LITELLM_MASTER_KEY=$(kubectl get secret litellm-secrets -n llm-serving \
  -o jsonpath='{.data.LITELLM_MASTER_KEY}' | base64 -d)
```


