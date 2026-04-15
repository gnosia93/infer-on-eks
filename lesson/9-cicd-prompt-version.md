
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
