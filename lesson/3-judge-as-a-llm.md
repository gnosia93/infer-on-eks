## LLM-as-a-Judge ##

"LLM의 출력을 또 다른 LLM이 채점/비교하게 하는" 평가 방식으로, 사람이 일일이 라벨링하는 비용을 낮추면서도 BLEU/ROUGE 같은 표면적 지표보다 의미 기반 평가를 할 수 있다. 

### 1. 기본 세 가지 패턴 ###

#### Pointwise (단일 점수 매기기) ####
응답 하나를 주고 기준별로 점수를 매기게 함. 예: 정확성 15, 유용성 15.
* 장점: 절대 평가 가능, 여러 모델을 독립적으로 비교.
* 단점: 점수 분포가 판정 모델에 따라 편향됨. 보통 4~5에 몰리는 경향(positivity bias).

#### Pairwise (두 응답 비교) ####
같은 프롬프트에 대한 두 모델/버전의 답을 주고 "어느 쪽이 더 나은지" 고르게 함. A/B/Tie.
* 장점: 상대 평가라 점수 보정 필요 없고, 사람 평가와 가장 상관관계가 높다고 알려져 있음 (Chatbot Arena 방식).
* 단점: N개 모델 비교하려면 쌍 수가 많아짐. 위치 편향(앞에 놓인 답을 선호) 존재.

#### Reference-based (정답 비교) ####
정답(또는 이상적 답변)과 응답을 함께 주고 "의미적으로 일치하는지" 판단.
* RAG의 답변 정확성, QA 평가에 적합.

### 2. 평가 기준(Criteria) 정의 ###

* Correctness: 사실이 맞는가, 정답과 의미가 같은가
* Faithfulness / Groundedness: 제공된 context(RAG)만으로 답했는가, 환각 없는가
* Relevance: 질문에 실제로 답하고 있는가
* Completeness: 빠진 정보 없이 충분한가
* Coherence / Fluency: 논리적이고 읽기 좋은가
* Safety / Tone: 부적절한 내용이나 톤 문제 없는가

한 judge가 여러 기준을 동시에 채점하기보단, 기준별로 나눠 호출하거나 각 기준의 점수를 JSON으로 구조화하는 것이 좋다.


### 3. 샘플 코드 ###
```
import json
import re
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="dummy")
MODEL = "Qwen/Qwen2.5-32B-Instruct"  # 실제 서빙 중인 모델명으로

SYSTEM_PROMPT = """당신은 AI 응답 품질 평가 전문가입니다.
- 점수는 엄격하게 매기세요. 모든 항목에 만점을 주는 경향을 피하세요.
- 답변의 길이가 아닌 내용의 질을 평가하세요.
- 반드시 지정된 JSON 형식만 출력하세요."""

USER_TEMPLATE = """다음 답변을 평가하세요.

[질문]
{question}

[답변]
{answer}

[평가 기준]
- 정확성(correctness): 사실 오류가 없는가
- 완전성(completeness): 핵심 내용이 빠짐없이 포함됐는가
- 실용성(practicality): 질문자가 실제로 활용할 수 있는 정보인가

각 기준을 1~5점으로 평가하세요.
출력은 반드시 아래 JSON 스키마만 따르세요. 다른 텍스트 금지.

{{
  "correctness": {{"reason": "<간결한 근거>", "score": <1-5>}},
  "completeness": {{"reason": "<간결한 근거>", "score": <1-5>}},
  "practicality": {{"reason": "<간결한 근거>", "score": <1-5>}},
  "overall": <1-5 평균 또는 종합>
}}"""


def _extract_json(text: str) -> dict:
    """코드펜스나 앞뒤 잡음이 있어도 JSON만 뽑아서 파싱."""
    # ```json ... ``` 제거
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    # 가장 바깥 중괄호 영역만 추출 (보수적)
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError(f"No JSON found in: {text[:200]}")
    return json.loads(match.group(0))


def llm_judge(question: str, answer: str) -> dict:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_TEMPLATE.format(
                question=question, answer=answer
            )},
        ],
        temperature=0,
        max_tokens=600,
        # vLLM 최신 버전이면 JSON 모드 사용
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content
    return _extract_json(content)


if __name__ == "__main__":
    result = llm_judge(
        question="EFA와 일반 네트워크의 차이점은?",
        answer="EFA는 OS bypass로 저지연 통신을 제공합니다.",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
```
* 평가 LLM은 평가 대상 모델보다 같거나 더 강한 모델을 써야 한다. (보통 GPT-4, Claude 등)
* "자기 편향(self-bias)"은 같은 모델뿐 아니라 같은 패밀리(예: GPT-4o judge가 GPT-4 답변 선호)에서도 나타난다.
* Pairwise에서 답변 순서를 바꿔서 2번 평가하면 위치 편향(position bias)을 줄일 수 있다.
* 길이 편향(Length bias) - Judge는 긴 답을 선호하는 경향이 있다.
* Judge 자체의 검증 - "golden set 50~200개로 judge와 사람 라벨의 상관관계(Spearman/Cohen's kappa)를 확인"


### 4. 평가 도구 ###
프로덕션에서는 사용자 요청과 LLM 응답을 로깅하고, 로그중 일부를 샘플링하여 비동기로 백그라운드에서 LLM Judge를 돌리고, 결과를 Prometheus 메트릭으로 수집하는 방식으로 운영한다.
샘플링 전략은 균등 랜덤 외에 "사용자 피드백이 부정적인 건", "모델이 낮은 logprob으로 답한 건"처럼 weighted sampling을 섞으면 문제 탐지율이 올라간다.
Judge는 비용을 고려해야 함으로 전체의 1~5%만 샘플링하고, 회귀 테스트용 고정 데이터셋(수백 건)은 릴리스마다 100% 돌리는 이중 체계를 유지한다.

- Ragas: RAG 전용 메트릭(faithfulness, answer_relevancy, context_precision 등). Python.
- DeepEval: pytest-like 인터페이스, G-Eval 구현 포함.
- OpenAI Evals / promptfoo: 시나리오 기반 회귀 테스트.
- LangSmith / Langfuse / Arize Phoenix: 트레이싱 + 평가 통합, 대시보드 제공.
- MT-Bench / AlpacaEval: 사전 정의된 벤치마크 + judge 프롬프트 템플릿.







