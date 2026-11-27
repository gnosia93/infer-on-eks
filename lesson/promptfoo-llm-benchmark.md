# Promptfoo 기반 LLM 글쓰기 업무 성능 비교 벤치마크 가이드

상용 경량 모델(**GPT-4o-mini**, **Gemini Flash**)과 오픈 웨이트 모델(**Gemma 4 31B - Bedrock 및 EKS 자체 호스팅**)의 한국어 글쓰기 품질, 속도(Latency), 비용 효율성을 객관적으로 비교·검증하기 위한 `promptfoo` 구성 및 실행 스크립트입니다.

---

## 📌 파일 주요 구성 요약

| 섹션 | 핵심 내용 | 목적 및 활용 방안 |
| :--- | :--- | :--- |
| **1. 디렉토리 구조 및 사전 준비** | `promptfooconfig.yaml`, `prompts/`, `run_benchmark.sh` 구조 및 패키지 설치 | 벤치마크 환경 초기화 및 필수 패키지 세팅 |
| **2. 환경 변수 설정 (`.env`)** | AWS Bedrock(서울 리전), OpenAI, Google AI, 사내 EKS(vLLM) 엔드포인트 및 키 설정 | 4개 비교군 모델 API 동시 호출을 위한 인증 구성 |
| **3. 공통 글쓰기 프롬프트** | 역할(Role), 문체, 제약조건이 정의된 시스템/유저 프롬프트 템플릿 | 모든 모델에 동일한 조건을 부여하여 공정한 품질 비교 |
| **4. 핵심 설정 (`promptfooconfig.yaml`)** | 4개 프로바이더 연결 + 5대 실무 글쓰기 테스트 케이스 + 자동 채점(`assert`) 로직 | 비즈니스 이메일, 기술 블로그, 마케팅 카피, 보고서, 사과문 평가 |
| **5. 자동화 실행 스크립트** | 타임스탬프 기반 결과 저장(`results.json`) 및 HTML 리포트 자동 생성 셸 스크립트 | 원클릭 벤치마크 실행 및 브라우저 기반 결과 대시보드 확인 |
| **6. 의사결정 체크포인트** | Pass Rate(합격률), Latency(응답 속도), 월간 절감액(4,420만 원) 연계 판단 기준 | 인프라 전환(상용 API → EKS/Bedrock 오픈웨이트) 최종 승인 근거 마련 |

---

## 1. 프로젝트 디렉토리 구조

```text
llm-writing-benchmark/
├── .env                    # API 키 및 AWS/EKS 엔드포인트 설정
├── promptfooconfig.yaml    # Promptfoo 메인 평가 설정 파일
├── prompts/
│   └── writing_prompt.txt  # 공통 시스템 및 유저 프롬프트 템플릿
├── run_benchmark.sh        # 벤치마크 자동 실행 및 리포트 추출 스크립트
└── results/                # 평가 결과(JSON, HTML) 저장 디렉토리
```

### 사전 설치 명령어
```bash
npm install -g promptfoo
mkdir -p llm-writing-benchmark/prompts llm-writing-benchmark/results
cd llm-writing-benchmark
```

---

## 2. 환경 변수 설정 (`.env`)

테스트 실행 전 아래 내용을 `.env` 파일로 저장하고 실제 키와 엔드포인트를 입력합니다.

```env
# 1. AWS Bedrock (서울 리전 - Gemma 4 31B 등 오픈웨이트 모델용)
AWS_REGION=ap-northeast-2
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key

# 2. OpenAI (GPT-4o-mini 비교군)
OPENAI_API_KEY=your_openai_api_key

# 3. Google AI (Gemini Flash 비교군)
GEMINI_API_KEY=your_gemini_api_key

# 4. 사내 EKS 자체 호스팅 엔드포인트 (g7e.2xlarge / 4xlarge + vLLM OpenAI 호환 API)
EKS_VLLM_BASE_URL=http://internal-eks-llm-alb.ap-northeast-2.elb.amazonaws.com/v1
EKS_VLLM_API_KEY=dummy-key-or-internal-token
```

---

## 3. 공통 글쓰기 프롬프트 (`prompts/writing_prompt.txt`)

모든 모델에 동일한 조건으로 글쓰기를 지시하기 위한 프롬프트 파일입니다.

```text
[시스템 지침]
당신은 한국어 비즈니스 커뮤니케이션 및 콘텐츠 제작 전문가입니다.
주어진 [업무 유형], [주제 및 핵심 내용], [타겟 독자], [분량 제한]에 맞춰 자연스럽고 설득력 있는 글을 작성하세요.
불필요한 인사말이나 부연 설명 없이 결과물 본문만 출력하세요.

[작성 요청]
- 업무 유형: {{task_type}}
- 주제 및 핵심 내용: {{topic}}
- 타겟 독자: {{audience}}
- 분량 및 형식 조건: {{constraints}}
```

---

## 4. Promptfoo 메인 설정 (`promptfooconfig.yaml`)

4개 환경(상용 경량 2종 + 오픈 웨이트 2종)을 동시에 호출하고, **규칙 기반(길이/금지어/응답속도)** 및 **LLM-as-a-Judge(한국어 자연스러움/논리성)** 방식으로 자동 채점합니다.

```yaml
description: "한국어 비즈니스 글쓰기 업무 성능 비교 (상용 경량 vs Gemma 4 31B)"

prompts:
  - file://prompts/writing_prompt.txt

# 1. 비교 대상 모델 (Providers)
providers:
  - id: openai:gpt-4o-mini
    label: "① 상용_GPT-4o-mini"
    config:
      temperature: 0.7
      max_tokens: 1500

  - id: google:gemini-2.5-flash
    label: "① 상용_Gemini-Flash"
    config:
      temperature: 0.7
      maxOutputTokens: 1500

  - id: bedrock:google.gemma-4-31b-it-v1:0 # 실제 Bedrock 콘솔의 모델 ID로 확인 후 기입
    label: "② Bedrock_Gemma-4-31B"
    config:
      region: ap-northeast-2
      temperature: 0.7
      max_gen_len: 1500

  - id: openai:chat:google/gemma-4-31b-it
    label: "③ EKS_vLLM_Gemma-4-31B"
    config:
      apiBaseUrl: ${EKS_VLLM_BASE_URL}
      apiKey: ${EKS_VLLM_API_KEY}
      temperature: 0.7
      max_tokens: 1500

# 2. 공통 평가 기준 (Default Assertions)
defaultTest:
  options:
    # 채점관(Judge) 모델은 객관성을 위해 상위 모델 지정
    provider: openai:gpt-4o
  assert:
    # 응답 속도 검증 (글쓰기 업무 체감 품질 기준 10초 이내)
    - type: latency
      threshold: 10000
    # AI 특유의 불필요한 서론 출력 방지
    - type: not-contains
      value: "알겠습니다."
    - type: not-contains
      value: "작성해 드리겠습니다"

# 3. 실무 글쓰기 5대 테스트 케이스
tests:
  - description: "Case 1. B2B 비즈니스 제안 이메일"
    vars:
      task_type: "B2B 영업/제안 이메일"
      topic: "기존 온프레미스 고객사 대상 클라우드 비용 40% 절감 컨설팅 및 PoC 무상 지원 안내"
      audience: "중견기업 IT 인프라 팀장"
      constraints: "제목 포함, 정중하고 신뢰감 있는 비즈니스 톤, 공백 포함 500자~700자 이내"
    assert:
      - type: javascript
        value: "output.length >= 450 && output.length <= 750"
      - type: llm-rubric
        value: "한국어 비즈니스 격식체(하십시오체/해요체 일관성)가 자연스럽고, 비용 절감 혜택과 PoC 제안이 명확히 전달되는가?"

  - description: "Case 2. IT 기술 블로그 요약 및 아티클"
    vars:
      task_type: "테크 블로그 본문 작성"
      topic: "EKS 환경에서 GPU Zonal RI와 vLLM을 활용해 오픈 웨이트 LLM 서빙 비용을 최적화한 아키텍처 소개"
      audience: "백엔드 및 MLOps 엔지니어"
      constraints: "소제목 3개 포함, 마크다운 형식, 전문 용어의 자연스러운 한국어 병기, 800자 내외"
    assert:
      - type: contains
        value: "##"
      - type: llm-rubric
        value: "기술적 개념(EKS, Zonal RI, vLLM)이 왜곡 없이 정확하게 설명되었으며, 번역투가 아닌 실무 엔지니어가 쓴 듯한 자연스러운 문체인가?"

  - description: "Case 3. 프로모션 마케팅 카피라이팅"
    vars:
      task_type: "앱 푸시 및 배너 마케팅 카피"
      topic: "신규 가입자 대상 첫 달 구독료 0원 및 AI 글쓰기 템플릿 50종 무료 제공 이벤트"
      audience: "2030 직장인 및 대학생"
      constraints: "메인 카피 1줄(25자 이내), 서브 카피 1줄(45자 이내), 행동 유도 버튼(CTA) 문구 1개 포함"
    assert:
      - type: llm-rubric
        value: "타겟 독자의 클릭을 유도하는 매력적인 후킹 문구인가? 제약 조건(메인/서브/CTA 구분 및 간결함)을 정확히 준수했는가?"

  - description: "Case 4. 경영진 보고용 Executive Summary"
    vars:
      task_type: "임원 보고용 핵심 요약문"
      topic: "상용 LLM API 월 9,800만 원 지출 구조를 EKS 자체 호스팅(월 5,300만 원)으로 전환 시 연간 5.3억 원 절감 기대. 단, 1년 RI 약정 리스크 및 초기 MLOps 구축 공수 1개월 소요."
      audience: "CFO 및 CTO"
      constraints: "개조식(Bullet point) 사용, 결론부터 제시(두괄식), 리스크 및 대응 방안 포함, 400자 이내"
    assert:
      - type: javascript
        value: "output.length <= 450"
      - type: llm-rubric
        value: "수치(9,800만 원, 5,300만 원, 5.3억 원) 왜곡이 전혀 없으며, 임원 보고에 적합한 간결한 개조식 문체로 작성되었는가?"

  - description: "Case 5. 서비스 장애 고객 사과 공지문"
    vars:
      task_type: "긴급 서비스 장애 사과문"
      topic: "오전 10시~10시 40분(40분간) 외부 API 연동 지연으로 인한 문서 자동 생성 기능 오류 발생 및 복구 완료, 재발 방지 대책 안내"
      audience: "유료 구독 중인 일반 B2C 고객"
      constraints: "진정성 있는 사과, 장애 시간 및 원인 투명 공개, 보상안(이용권 3일 연장) 명시, 600자 내외"
    assert:
      - type: contains
        value: "40분"
      - type: contains
        value: "3일"
      - type: llm-rubric
        value: "고객의 불편에 공감하는 정중하고 책임감 있는 어조이며, 변명조가 느껴지지 않는가?"
```

---

## 5. 실행 및 결과 리포트 스크립트 (`run_benchmark.sh`)

```bash
#!/bin/bash
set -e

# 환경 변수 로드
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
OUTPUT_JSON="results/benchmark_${TIMESTAMP}.json"
OUTPUT_HTML="results/benchmark_${TIMESTAMP}.html"

echo "🚀 LLM 글쓰기 성능 벤치마크를 시작합니다..."

# 1. 평가 실행 및 JSON/HTML 동시 추출
promptfoo eval -c promptfooconfig.yaml -o "$OUTPUT_JSON" -o "$OUTPUT_HTML" --no-cache

echo "✅ 평가 완료!"
echo "📊 JSON 결과: $OUTPUT_JSON"
echo "🌐 HTML 리포트: $OUTPUT_HTML"

# 2. 브라우저에서 대시보드 즉시 확인 (로컬 실행 시)
# promptfoo view
```

### 실행 방법
```bash
chmod +x run_benchmark.sh
./run_benchmark.sh
```

---

## 6. 인프라 전환 의사결정 체크포인트

벤치마크 완료 후 생성된 HTML 리포트에서 아래 3가지 지표를 확인하여 아키텍처 전환 여부를 결정합니다.

1. **품질 합격률 (Pass Rate):** `Gemma 4 31B`의 전체 테스트 통과율이 상용 경량 모델(`GPT-4o-mini` / `Gemini Flash`) 대비 **90% 이상** 수준인지 확인합니다. 특히 **Case 4(수치 왜곡 여부)**와 **Case 1, 5(한국어 존댓말·뉘앙스 자연스러움)** 항목의 점수를 중점적으로 비교합니다.
2. **응답 지연 시간 (Latency):** `EKS_vLLM_Gemma-4-31B`의 평균 응답 속도가 `g7e.2xlarge` 환경에서 목표 SLA(예: 5~8초 이내)를 충족하는지 확인합니다. 긴 글 작성 시 토큰 생성 속도(TPS)가 느리다면 `g7e.4xlarge` 또는 텐서 병렬화(Tensor Parallelism) 구성을 검토합니다.
3. **비용 대비 효용성:** 품질과 속도가 실무 투입 기준을 통과한다면, **EKS + 1년 Zonal RI(`g7e.2xlarge`)** 전환을 통해 **월 약 4,420만 원(연간 약 5.3억 원)의 인프라 비용 절감**을 즉시 실행할 수 있습니다.
