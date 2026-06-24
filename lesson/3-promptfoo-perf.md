말씀하신 대로 **AI 서비스나 애플리케이션 관점에서 "LLM 성능 평가"의 핵심은 "프롬프트를 바꾸거나 모델을 바꿨을 때, 정답을 제대로 잘 내뱉는가(응답 품질)"**가 맞습니다. 이를 업계에서는 LLM Evaluation(LLM Eval) 또는 품질 평가라고 부릅니다.
인프라적인 부하 테스트(Locust 등) 외에, 질문하신 **'응답 품질'**을 제대로 평가하기 위해 EKS 환경 및 LLM 파이프라인에서 실제로 사용하는 핵심 방법론과 프레임워크를 정리해 드릴게요.
## 1. 응답 품질 평가가 어려운 이유
전통적인 소프트웨어는 인풋(1+1) -> 아웃풋(2)으로 정답이 명확하지만, LLM은 똑같은 질문을 해도 매번 답변이 달라질 수 있고(생성형의 특성), "좋은 답변"에 대한 기준이 주관적이기 때문입니다.
## 2. 품질 평가의 3가지 핵심 방법론
프롬프트나 모델(예: Llama 3 ‭$\rightarrow$‬ Mistral)을 변경했을 때 품질을 검증하는 방법은 크게 세 가지로 나뉩니다.
### ① LLM-as-a-Judge (가장 대세인 방법)
사람 대신 가장 똑똑한 모델(예: GPT-4o, Claude 3.5 Sonnet 등)을 판사(Judge)로 고용하여, 프롬프트/모델 변경 전후의 답변 품질을 점수 매기게 하는 방식입니다.
•	방법: 정답 가이드라인(Ground Truth)과 변경된 모델의 답변을 판사 모델에게 주고 "정확성, 유용성, 무해성 점수를 1~5점으로 판정해줘"라고 요청합니다.
•	장점: 사람보다 비용이 훨씬 저렴하고 자동화(CI/CD 연동)가 가능합니다.
### ② 벤치마크 데이터셋 활용 (정량 평가)
특정 도메인에 맞춤형 데이터셋을 구축해 두고, 프롬프트 변경 시 점수가 떨어지지 않는지 체크합니다.
•	RAG 시스템 평가 (Ragas 프레임워크): 만약 회사 문서를 기반으로 답변하는 시스템이라면, 문서를 제대로 참조했는지(Context Relevance), 답변에 거짓말(환각)은 없는지(Faithfulness)를 수학적/품질적으로 점수화합니다.
•	일반 능력 평가: MMLU(상식), GSM8K(수학 연산) 같은 공개 벤치마크 셋을 활용해 모델 변경 후 기본 능력이 유지되는지 검증합니다.
### ③ 사람 기반 평가 (Human-in-the-Loop)
최종 서비스 배포 전에는 결국 사람이 검증해야 합니다.
•	A/B 테스트 / 전시장(Arena) 방식: 유저에게 A 프롬프트의 결과와 B 프롬프트의 결과를 블라인드로 보여주고, 어떤 답변이 더 마음에 드는지 투표하게 만듭니다.
## 3. 이걸 EKS 인프라/파이프라인에서 어떻게 구현하나요?
실무에서는 프롬프트를 수정하거나 모델 버전을 올릴 때마다 사람이 일일이 테스트할 수 없으므로, **"LLM CI/CD 파이프라인"**을 구축합니다.
	1.	Prompt/Model 변경: 개발자가 프롬프트 파일을 수정하거나 새 모델 코드를 깃허브(GitHub)에 푸시합니다.
	2.	EKS에서 평가 파드 실행: GitHub Actions 같은 CI 도구가 EKS 클러스터에 **품질 평가 전용 파드(Job)**를 띄웁니다.
	3.	자동 평가 수행: Ragas나 Promptflow 같은 프레임워크가 준비된 테스트 질문 100개를 새 프롬프트로 찔러보고, 나온 답변들을 'LLM-as-a-Judge' 방식으로 평가합니다.
	4.	리포트 발행: "이번 프롬프트 변경으로 인해 정확도가 85%에서 92%로 향상되었습니다. 배포를 승인합니다."라는 리포트를 개발자에게 보여줍니다.
요약하자면
질문하신 내용이 정확히 맞습니다. 인프라가 버티는 성능(Throughput)도 중요하지만, 프롬프트나 모델을 바꿨을 때 **"정답을 얼마나 왜곡 없이, 기준에 맞게 잘 내뱉는가"**를 평가하는 품질 평가(Evaluation) 프레임워크(Ragas, Promptflow, LangSmith 등)를 도입하는 것이 LLM 서비스 운영의 핵심입니다.


## 모델 성능 평가 하기 ##

### 1. promptfoo 설치 ### 
promptfoo를 사용하려면 먼저 Node.js를 설치해야 합니다. 그다음 npm(Node Package Manager)으로 promptfoo와 Amazon Bedrock SDK를 설치합니다.

```
brew install node
node --version
npm install promptfoo
npm install @aws-sdk/client-bedrock-runtime
```

### 2. 프로젝트 초기화 ###
작업 디렉터리를 만들고 promptfoo를 초기화합니다. 참고로 npx 는 Node.js 용 패키지 실행 도구입니다.
```
mkdir llm-eval && cd llm-eval
npx promptfoo init
```
init 를 실행한 후, Compare prompts and models 메뉴을 선택합니다.    

![](https://github.com/gnosia93/lg-agentic-ai/blob/main/lesson/images/promptfoo-init-1.png)

[AWS Bedrock] Claude, Llama, Titan .. 메뉴를 선택한다.  

![](https://github.com/gnosia93/lg-agentic-ai/blob/main/lesson/images/promptfoo-init-2.png)

프로젝트 디렉토리에 README.md 파일과 promptfootconfig.yaml 파일이 생성된 것을 확인한다.  

![](https://github.com/gnosia93/lg-agentic-ai/blob/main/lesson/images/promptfoo-init-3.png)

생성된 promptfooconfig.yaml 설정 파일을 확인한다.
  
![](https://github.com/gnosia93/lg-agentic-ai/blob/main/lesson/images/promptfoo-init-4.png)


### 3. 테스트 시나리오 작성하기 ### 

Bedrock 이 제공하는 모델들을 평가하기 위해서 promptfooconfig.yaml 파일의 내용을 아래 시나라오로 대체 합니다.

```
cat <<EOF > promptfooconfig.yaml
description: AWS Bedrock 모델 비교 평가

prompts:
  - |
    다음 질문에 한국어로 답변해줘.
    정확하고 간결하게 답변할 것.

    질문: {{question}}

# 모델 프러바이더 설정
providers:
  # Sonnet 4.6 (global. 프리픽스)
  - id: bedrock:global.anthropic.claude-sonnet-4-6
    config: { region: ap-northeast-2, temperature: 0, max_tokens: 1024 }
  # Haiku 3 (apac. 프리픽스)
  - id: bedrock:apac.anthropic.claude-3-haiku-20240307-v1:0
    config: { region: ap-northeast-2, temperature: 0, max_tokens: 1024 }
  # Nova Pro (apac. 프리픽스)
  - id: bedrock:apac.amazon.nova-pro-v1:0
    config:
      region: ap-northeast-2
      interfaceConfig: { temperature: 0, max_new_tokens: 1024 }

# 평가 모델 설정
defaultTest:
  options:
    provider:
      id: bedrock:global.anthropic.claude-opus-4-8
      config: { region: ap-northeast-2, temperature: 0 }
  assert:
    # cost 는 지원하지 않으므로 주석처리한다. 
    #- type: cost
    #  threshold: 0.05
    - type: latency
      threshold: 10000
      metric: 응답속도
    # 한국어로 답변했는가
    - type: llm-rubric
      value: "답변이 한국어로 작성되어 있는가?"
      metric: 언어
    # 기술적 정확성
    - type: llm-rubric
      value: "기술적으로 틀린 내용이 없는가?"
      metric: 정확성
    # 구조화된 답변인가
    - type: llm-rubric
      value: "답변이 논리적으로 구조화되어 있고, 핵심을 먼저 말하는가?"
      metric: 구조
    # 간결성 (너무 길지 않은가)
    - type: javascript
      value: "output.length < 3000 ? 1.0 : Math.max(0, 1 - (output.length - 3000) / 5000)"
      metric: 간결성

tests:
  - vars:
      question: "쿠버네티스에서 파드와 디플로이먼트의 차이점은?"
    threshold: 0.7
    assert: # 아래 기준 1개 + defaultTest 5개에 대해서 대해서 test 를 수행한다.
      - type: llm-rubric
        value: "파드와 디플로이먼트의 차이를 정확히 설명하고, 실무 관점의 예시가 포함되어 있는가?"
        metric: 완전성 

  - vars:
      question: "REST API와 GraphQL의 장단점을 비교해줘"
    threshold: 0.7
    assert:
      - type: llm-rubric
        value: "두 기술의 장단점이 균형 있게 설명되어 있는가?"
        metric: 균형성
      - type: contains
        value: "GraphQL"
        metric: 문자열포함
EOF
```
promptfoo 설정은 크게 4가지 부분(섹션)으로 이뤄져 있습니다.

가장 먼저 나오는 prompts에는 모든 모델에게 동일하게 주어지는 질문 틀이 담겨 있습니다. "한국어로, 정확하고 간결하게 답해 달라"는 지시와 함께 {{question}}이라는 빈칸이 있는데, 이 자리에 tests 섹션에 설정된 실제 질문이 하나씩 끼워져 들어갑니다. 덕분에 질문만 바꿔 가면서 모든 모델을 똑같은 조건에서 시험할 수 있습니다.

providers 에서는 평가할 대상 모델을 정의합니다. 고성능 모델인 Claude Sonnet 4.6, 빠르고 가벼운 Claude Haiku 3, 그리고 아마존이 만든 Nova Pro 를 사용하였습니다. 세 모델 모두 서울 리전에서 실행되고, 매번 답변이 들쭉날쭉하지 않도록 temperature를 0으로 맞춰 무작위성을 없앴습니다. 한 가지 눈여겨볼 점은 Nova의 경우 답변 길이를 정하는 설정 키 이름이 max_new_tokens로, Claude 계열이 쓰는 max_tokens와 다르다는 것입니다.

세 번째로 나오는 설정은 defaultTest입니다. 여기에는 모든 질문에 공통으로 적용되는 채점 기준이 모여 있습니다. 채점 항목은 모두 다섯 가지로, 10초 안에 답했는지를 보는 응답 속도, 한국어로 답했는지를 보는 언어, 기술적으로 틀린 내용이 없는지를 보는 정확성, 논리적으로 풀어냈는지를 보는 구조, 그리고 답변이 너무 길지 않은지를 보는 간결성입니다. 이 항목들은 채점 방식이 둘로 나뉩니다. 언어와 정확성, 구조처럼 정답이 딱 떨어지지 않는 주관적인 기준은, 사람이 아니라 또 다른 모델인 Claude Opus 4.8이 답변을 읽고 판단합니다. AI가 다른 AI의 답변을 평가하는 이른바 LLM-as-a-judge 방식입니다. 

반면 응답 속도와 간결성은 평가 모델과 무관하게 promptfoo가 직접 처리합니다. 응답에 걸린 시간을 재거나 글자 수를 세는 일은 코드만으로 객관적으로 판정할 수 있기 때문입니다. 특히 간결성은 답변이 3000자를 넘어가기 시작하면 점수가 점점 깎이도록 계산식을 넣어 두었습니다. 참고로 비용을 재는 항목도 있었지만, 지원되지 않아 주석으로 막아 둔 상태입니다.

채점 항목마다 붙어 있는 metric 태그는 각 결과에 이름표를 달아 주는 역할을 합니다. 평가가 끝나면 promptfoo가 이 이름표별로 점수를 묶어 집계해 주기 때문에, 모델마다 정확성, 간결성, 응답 속도 같은 항목에서 어느 쪽이 강하고 약한지를 한눈에 비교할 수 있습니다. 합격 여부를 좌우하는 설정이 아니라, 결과를 분류해 보여 주기 위한 이름표라고 이해하면 됩니다

마지막 tests에는 모델에게 실제로 던질 질문이 들어 있습니다. 각 질문에는 앞서 정한 공통 기준 다섯 개가 그대로 적용되고, 거기에 더해 그 질문에만 적용되는 기준이 하나씩 덧붙습니다. 예를 들어 쿠버네티스의 파드와 디플로이먼트의 차이를 묻는 질문에는 차이를 정확히 설명하면서 실무 예시까지 들었는지를 보는 완전성 기준이 추가되고, REST API와 GraphQL을 비교하라는 질문에는 양쪽 장단점을 어느 한쪽에 치우치지 않고 균형 있게 다뤘는지를 보는 기준과 답변에 "GraphQL"이라는 단어가 실제로 들어 있는지를 확인하는 기준이 함께 붙습니다. 각 질문에 적힌 0.7이라는 숫자는 합격선으로, 전체 채점 점수가 70퍼센트를 넘어야 통과로 인정됩니다.

#### 왜 Thresdhold 는 0.7 인가? ####

0.7 이라는 합격선은 어떤 절대적인 공식이 있어서가 아니라, 경험적으로 적당하다고 여겨지는 균형점이기 때문에 자주 쓰입니다. 기준을 너무 높게 1.0이나 0.9로 잡으면 사소한 흠 하나에도 멀쩡한 답변이 탈락해 버리고, 반대로 0.5처럼 낮게 잡으면 절반만 맞아도 통과해 변별력이 사라집니다. 0.7은 "대부분의 기준을 만족하면서 약간의 부족함은 눈감아 주는" 정도의 선이라, 지나치게 깐깐하지도 너무 느슨하지도 않은 현실적인 합격 기준으로 통용됩니다. 그래서 평가 초기에 별다른 근거가 없을 때 무난한 출발점으로 0.7을 두고, 이후 결과를 보면서 더 높이거나 낮추는 식으로 조정하는 경우가 많습니다.

#### 이 밖의 assert 연산자들 ####
이 글에서는 llm-rubric, latency, javascript, contains 정도의 연산자만 다뤘지만, promptfoo는 이 밖에도 다양한 assert 연산자를 제공합니다. 코드로 딱 떨어지게 검증하는 결정적 연산자로는 출력이 특정 값과 정확히 일치하는지 보는 equals, 정규식 패턴에 맞는지 보는 regex, 유효한 JSON인지 확인하는 is-json, 호출 비용이 기준 이하인지 보는 cost 등이 있습니다. 또 채점용 모델(LLM judge)의 연산자로는 답변의 사실관계를 따지는 factuality, 질문과의 관련성을 보는 answer-relevance, 여러 기준을 단계적으로 평가하는 g-eval 등이 있습니다. 각 연산자의 정확한 동작과 설정 방법은 promptfoo 공식 문서(https://www.promptfoo.dev/docs/configuration/expected-outputs/)에서 확인할 수 있습니다.


### 4. 테스트 실행하기 ###
다음과 같이 eval 모드로 테스트를 실행합니다. @latest를 붙여 최신 버전의 promptfoo를 사용했으며, --no-cache 옵션을 주어 이전 실행 결과를 재사용하지 않고 모든 요청을 모델에 새로 보내도록 했습니다.
```
npx promptfoo@latest eval --no-cache
```
[결과]
![](https://github.com/gnosia93/langgraph-agentic-ai/blob/main/lesson/images/promptfoo_result.png)

세 개의 Bedrock 모델(Claude Sonnet 4.6, Claude 3 Haiku, Nova Pro)에 동일한 프롬프트로 두 가지 질문을 던져 비교한 평가입니다. 총 6개 테스트(3개 모델 × 2개 질문)가 모두 통과했고, 실패나 오류는 없었습니다. 토큰은 총 22,742개를 사용했는데 이 중 대부분(19,782개)이 답변 채점에 쓰였고, 응답 길이는 Sonnet이 가장 길었습니다.

이번 평가에서 특히 눈여겨볼 점은 채점에 들어간 토큰량입니다. Grading 항목의 19,782 토큰은 모두 채점을 담당한 Opus(LLM judge)가 사용한 것으로, 답변 생성에 쓰인 2,960 토큰의 6배가 넘습니다. 단순히 점수만 매기는 작업치고는 꽤 많아 보이지만, 그 구조를 들여다보면 이유가 분명합니다.

채점은 응답 하나당 한 번이 아니라 설정한 rubric 개수만큼 반복됩니다. 이번 설정에는 공통 기준(언어·정확성·구조)에 질문별 추가 기준(완전성·균형성)까지 더해져 있어서, 6개의 응답에 대해 스무 번이 넘는 채점 요청이 일어났습니다. 게다가 매 채점마다 "채점 지시문 + 평가 기준 + 모델이 생성한 답변 전문"이 통째로 입력으로 들어가기 때문에, 답변이 길수록 그 긴 답변이 채점할 때마다 judge의 입력으로 다시 들어가면서 토큰이 빠르게 불어납니다. 여기에 judge로 Opus 같은 대형 모델을 쓰면 토큰 단가까지 높아져 비용 부담이 한층 커집니다.

이 비용은 몇 가지 방법으로 줄일 수 있습니다. 우선 채점 모델을 Sonnet이나 Haiku처럼 더 가벼운 모델로 바꾸면 토큰 단가를 크게 낮출 수 있고, rubric을 꼭 필요한 것만 남기거나 여러 기준을 하나로 합치면 채점 호출 횟수 자체가 줄어듭니다. 또한 평가 대상 답변의 max_tokens를 제한하면 judge가 읽어야 할 입력이 짧아지고, 규칙으로 판단할 수 있는 항목은 llm-rubric 대신 javascript나 contains 같은 비-LLM 검증으로 대체할 수 있습니다.

정리하면, LLM judge는 "응답 수 × rubric 수"만큼 답변 전문을 반복해서 읽기 때문에 채점 토큰이 답변 생성 토큰보다 훨씬 많아지는 것이 일반적입니다. judge 모델을 가볍게 바꾸고 rubric을 정리하는 것만으로도 토큰과 비용을 크게 아낄 수 있습니다.

#### 마지막으로, eval 모드에서는 드러나지 않는 모델 간의 세부 차이를 확인하기 위해 아래와 같이 view 모드로 promptfoo를 다시 실행합니다. ####

```
npx promptfoo@latest view
```
[결과]
![](https://github.com/gnosia93/langgraph-agentic-ai/blob/main/lesson/images/promptfoo-view-1.png)

터미널의 eval 결과와 달리, promptfoo view로 띄운 웹 UI는 평가 결과를 한층 더 깊이 있게 보여줍니다. 각 셀 헤더에는 지표(metric)별 점수가 별도로 표시되고 모델들이 완전성, 구조, 언어, 정확성, 간결성 같은 항목에서 각각 몇 점을 받았는지 나란히 비교할 수 있습니다. 여기서 어떤 모델이 어느 부분에서 강하고 또 어디가 약한지를 세분화해서 살펴볼 수 있습니다.

여기서 눈에 띄는 빨간색 글씨는 채점을 담당한 LLM(이번 평가에서는 Opus)이 남긴 평가 코멘트입니다. llm-rubric 기준으로 점수를 매기면서 "왜 이런 점수를 줬는지" 그 이유를 함께 적어 주는데요. 예를 들어 "결론을 먼저 말하지 않고 정의부터 나열했다"처럼 구체적인 감점 사유가 그대로 드러납니다. 단순히 점수만 확인하는 데서 그치지 않고, 그 점수가 나온 채점 논리까지 들여다볼 수 있다는 점이 이 화면의 가장 큰 장점입니다.


