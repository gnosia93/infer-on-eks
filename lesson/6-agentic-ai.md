L6. LangGraph로 Agentic AI 만들기

6.1 왜 Agentic인가 (10분, 이론)
  - RAG의 한계: 단일 턴, 정적 흐름
  - Agentic = LLM이 스스로 판단하고 도구 쓰는 루프
  - ReAct 패턴: Reason → Act → Observe
  - LangGraph가 해결하는 것: 상태 그래프로 흐름 제어

6.2 첫 에이전트: Tool Calling (핸즈온)
  - @tool 데코레이터
  - ToolNode + 조건부 엣지
  - 실습: 간단한 계산/검색 도구 호출하는 에이전트

6.3 RAG를 에이전트 도구로 (L5와 연결)
  - L5에서 만든 RAG를 @tool로 감싸기
  - 에이전트가 "검색이 필요한지" 스스로 판단
  - 실습: 질문에 따라 RAG 쓸지 말지 결정하는 에이전트

6.4 상태와 메모리
  - LangGraph State: 그래프 전체에서 공유되는 상태
  - 단기 메모리: 대화 컨텍스트 (MessagesState)
  - 장기 메모리: 사용자 프로필, 선호도 (외부 저장소)
  - 실습: 이전 대화 기억하는 에이전트

6.5 세션과 영속성
  - Checkpointer: 대화 상태 저장/복구
  - 세션 ID 관리, 타임아웃
  - 실습: Redis/Postgres 체크포인터 붙이기

6.6 관측성: Langfuse
  - 왜 필요한가: 에이전트는 블랙박스. 디버깅 지옥
  - Trace, Span, Generation
  - 토큰/비용/레이턴시 추적
  - 실습: Langfuse 붙이고 실제 실행 분석

6.7 (선택) Open WebUI 연동
  - 만든 에이전트를 UI에 노출
  - 데모용
