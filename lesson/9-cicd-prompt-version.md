## 프롬프트 버전 관리 ##
가장 실용적인 방법은 프롬프트를 코드처럼 Git으로 관리하는 것이다.

### 프로젝트 구조 ###
```
repo/
├── prompts/
│   ├── system_prompt.txt          # 시스템 프롬프트
│   ├── rag_prompt.txt             # RAG용 프롬프트
│   └── summarize_prompt.txt       # 요약용 프롬프트
├── tests/
│   └── promptfooconfig.yaml       # 프롬프트 평가 설정
├── CHANGELOG.md                   # 프롬프트 변경 이력
└── app/
    └── agent.py                   # 프롬프트를 파일에서 로드
```

### 워크 플로우 ###
```
1. 프롬프트 수정
   prompts/system_prompt.txt 수정

2. 로컬에서 평가
   npx promptfoo eval

3. PR 생성
   git add prompts/system_prompt.txt
   git commit -m "시스템 프롬프트: 답변 톤 변경 (v2.1)"
   git push → PR(Pull Request) 생성

4. CI에서 자동 평가 실행
   GitHub Actions가 promptfoo eval 실행
   → 기존 대비 품질 비교 결과를 PR 코멘트로 남김

5. 리뷰 & 머지
   평가 통과 + 리뷰 승인 → 머지

6. 문제 발생 시 롤백
   git revert → 이전 프롬프트로 즉시 복원
```
* "Pull Request"는 내가 push한 게 아니라, 메인 브랜치 관리자에게 "내 변경사항을 당겨가(pull) 주세요"라고 요청(request)한다는 의미이다. 내 입장에서는 push했지만, 메인 브랜치 입장에서는 내 코드를 pull해오는 거라서 Pull Request 인거으로 관점이 메인 브랜치 쪽에 있다. 참고로 GitLab에서는 이를 Merge Request(MR)라고 부른다. 

### GitHub 액션 (예시) ###
```
# .github/workflows/prompt-eval.yml
name: Prompt Evaluation

on:
  pull_request:
    paths:
      - 'prompts/**'

jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run Prompt Eval
        run: npx promptfoo@latest eval --ci
        env:
          AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}

      - name: Post Results to PR
        if: always()
        run: npx promptfoo@latest eval --ci --output-file results.json
```
