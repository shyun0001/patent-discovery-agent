"""PromptManager — 프롬프트 템플릿 (implementation_detail.md §4.3)."""
from __future__ import annotations

import json


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


TECH_ANALYSIS_PROMPT = """[시스템]
당신은 기술 특허 전문 분석가입니다.
연구 문서의 변경 사항을 분석하여 기술적으로 유의미한 변화를 식별합니다.

[지시]
다음은 연구 문서의 이전 버전과 변경된 버전 간의 차이(diff)입니다.
각 변경 사항을 분석하여 아래 기준에 따라 분류하세요.

## 변화 유형 분류 기준
- algorithm: 알고리즘/로직의 본질적 변경
- architecture: 시스템/모델 구조 변경
- data_structure: 데이터 처리 방식 변경
- optimization: 성능/효율 최적화
- new_feature: 완전히 새로운 기능 추가
- interface: API/인터페이스 변경 (일반적으로 특허성 낮음)
- bug_fix: 단순 버그 수정 (특허성 없음)
- refactor: 리팩토링/코드 정리 (특허성 없음)

## 유의미성 판단 기준 (0.0~1.0)
- 0.8~1.0: 핵심 기술 변경, 높은 특허 후보
- 0.5~0.7: 의미 있는 개선, 잠재 특허 후보
- 0.3~0.4: 일반적 개선, 특허성 낮음
- 0.0~0.2: 단순 변경, 특허성 없음

## Diff 내용
{diff_context}

## 출력 형식
반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트를 포함하지 마세요.
{{
  "tech_changes": [
    {{
      "change_type": "algorithm",
      "title": "변화를 한 줄로 요약한 제목",
      "description": "무엇이 어떻게 바뀌었는지 2~3문장",
      "original_summary": "이전 버전 요약",
      "changed_summary": "변경 버전 요약",
      "significance_score": 0.85,
      "is_patentable_candidate": true,
      "reasoning": "이 점수를 준 근거"
    }}
  ]
}}"""

INVENTION_EXTRACT_PROMPT = """[시스템]
당신은 한국 특허 명세서 작성 전문가입니다.
기술 변화 분석 결과를 바탕으로 잠재적 발명 포인트를 도출합니다.

[지시]
다음은 연구 문서에서 추출된 기술적으로 유의미한 변화 목록입니다.
이 변화들을 종합하여, 하나 이상의 발명 포인트를 도출하세요.

## 발명 포인트 도출 기준
1. 서로 연관된 기술 변화는 하나의 발명으로 묶을 수 있습니다
2. 독립적인 기술 변화는 별도의 발명으로 분리합니다
3. 각 발명은 "무엇을(What)" "어떻게(How)" "왜(Why)" 명확히 설명되어야 합니다
4. 발명의 명칭은 "~방법", "~장치", "~시스템" 형태로 작성합니다

## 기술 변화 목록
{tech_changes_json}

## 출력 형식
반드시 아래 JSON 형식으로만 응답하세요.
{{
  "invention_points": [
    {{
      "title": "도메인 특화 ~하는 방법",
      "summary": "발명의 핵심을 2~3문장으로 요약",
      "source_change_titles": ["근거가 된 기술 변화 제목"],
      "confidence_score": 0.82
    }}
  ]
}}"""

INVENTION_STRUCTURE_PROMPT = """[시스템]
당신은 한국 특허 명세서 작성 전문가이자 변리사입니다.
발명 포인트를 특허 명세서의 핵심 구성요소로 구조화합니다.

[지시]
다음 발명 포인트를 한국 특허 명세서 양식에 맞게 구조화하세요.

## 구조화 규칙

### 기술적 과제 (problem)
- "종래의 ~에서는 ~하는 문제가 있었다" 형식
- 구체적인 기술적 한계를 서술
- 정량적 데이터가 있으면 포함

### 해결 수단 (solution_means)
- "본 발명은 ~을(를) 제공한다" 형식
- 구체적 기술 구성을 단계별로 서술
- (1), (2), (3) 등 번호로 핵심 구성요소를 나열
- 추상적 표현 금지, 구현 가능한 수준으로 구체화

### 기대 효과 (effect)
- "본 발명에 의하면, ~" 형식
- 가능한 정량적 수치 포함 (예: "약 40% 향상")
- 종래 기술 대비 차별적 효과 강조

### 특허성 평가 (patentability)
각 항목(신규성, 진보성, 산업상 이용가능성)에 대해:
- HIGH / MEDIUM / LOW 판정
- 판정 근거를 1~2문장으로 설명
- 이 판정은 사전 지식 기반 추정이며, 실제 선행기술 검색 결과가 우선함

## 발명 포인트
{invention_point_json}

## 출력 형식
반드시 아래 JSON 형식으로만 응답하세요.
{{
  "technical_field": "인공지능 / 기계학습 / ...",
  "background_art": "종래 기술 요약",
  "problem": "...",
  "solution_means": "...",
  "effect": "...",
  "patentability": {{
    "novelty": {{"level": "HIGH", "reasoning": "..."}},
    "inventive_step": {{"level": "MEDIUM", "reasoning": "..."}},
    "industrial_applicability": {{"level": "HIGH", "reasoning": "..."}}
  }}
}}"""

SEARCH_QUERY_PROMPT = """[시스템]
당신은 특허 검색 전문가입니다.
발명의 구조화된 정보를 바탕으로 선행기술 검색 전략을 수립합니다.

[지시]
다음 발명 구조를 분석하여 선행기술 검색에 사용할 검색어를 생성하세요.

## 검색어 생성 규칙

### 한국어 검색어 (KIPRIS 실제 조회용 — 가장 중요)
- 핵심 기술 용어 중심, 조사·불용어 제외
- 국내 특허 명세서에서 통용되는 용어 사용 (예: "학습률" O, "러닝레이트" X)
- 2~4개 명사 조합 권장

### 영문 검색어 (발명신고서 참고용)
- 한국어 검색어의 정확한 기술 용어 번역
- 본 시스템에서는 실제 API 조회에 사용하지 않음 (검색 대상은 KIPRIS 국내 DB)

### 보조 검색어 (1차 검색 결과가 부족할 때 사용)
- 유사 개념, 동의어, 상위/하위 개념 포함
- 2~3개 변형 제공

### Boolean 검색식
- AND, OR 연산자를 활용한 통합 검색식

### IPC 코드
- 가장 관련성 높은 IPC 분류 코드 2~3개 (예: "G06N 3/08")
- 각 코드의 의미 설명 포함

## 발명 구조
{invention_structure_json}

## 출력 형식
반드시 아래 JSON 형식으로만 응답하세요.
{{
  "primary_kr": "...",
  "primary_en": "...",
  "secondary_kr": ["...", "..."],
  "secondary_en": ["...", "..."],
  "boolean_query": "...",
  "ipc_codes": [{{"code": "G06N 3/08", "description": "신경망의 학습 방법"}}]
}}"""

PRIOR_ART_SIMILARITY_PROMPT = """[시스템]
당신은 특허 선행기술 조사 전문가입니다.
본 발명과 KIPRIS에서 검색된 국내 선행 특허를 비교하여 중복 여부를 판단합니다.

[지시]
아래 "본 발명"과 "선행기술 목록"을 비교하여, 각 선행문헌마다
유사도와 중복/차별 포인트를 판정하세요.

## 판정 규칙

### 유사도 점수 (0.0~1.0)
- 0.8~1.0: 해결 과제와 핵심 구성이 실질적으로 동일 → 신규성 부정 우려
- 0.5~0.7: 기술 분야와 일부 구성이 겹침 → 진보성 다툼 가능
- 0.3~0.4: 같은 분야이나 구성·목적이 다름
- 0.0~0.2: 관련성 낮음

### 중복 우려 포인트 (overlapping_points)
- 선행문헌의 어떤 구성이 본 발명의 어떤 구성과 겹치는지 구체적으로 서술
- 겹치는 부분이 없으면 "없음"으로 기재

### 차별점 (differentiating_points)
- 본 발명에만 있는 구성요소·결합방식·적용 도메인·정량적 효과를 서술
- 발명신고서에 그대로 인용할 수 있는 문장으로 작성

## 주의사항
- 제공된 초록에 없는 내용을 추측하여 단정하지 마세요
- 초록만으로 판단이 어려우면 reasoning에 그 한계를 명시하세요
- 최종 특허성 판단은 변리사의 몫이며, 본 결과는 참고 자료임을 전제로 하세요

## 본 발명
{invention_structure_json}

## 선행기술 목록 (KIPRIS 검색 결과)
{patent_abstracts_json}

## 출력 형식
반드시 아래 JSON 형식으로만 응답하세요.
{{
  "assessments": [
    {{
      "application_number": "1020210012345",
      "similarity_score": 0.72,
      "risk_level": "MEDIUM",
      "overlapping_points": "...",
      "differentiating_points": "...",
      "reasoning": "..."
    }}
  ],
  "overall": {{
    "max_similarity": 0.72,
    "overall_risk": "MEDIUM",
    "key_differentiators": ["...", "..."]
  }}
}}"""


class PromptManager:
    """각 태스크별 프롬프트를 컨텍스트와 함께 완성한다."""

    SYSTEM_ROLE = "한국 특허 실무를 이해하는 기술 분석가"

    @staticmethod
    def build_tech_analysis_prompt(diff_context: str) -> str:
        return TECH_ANALYSIS_PROMPT.format(diff_context=diff_context)

    @staticmethod
    def build_invention_extract_prompt(tech_changes: list[dict]) -> str:
        return INVENTION_EXTRACT_PROMPT.format(tech_changes_json=_json(tech_changes))

    @staticmethod
    def build_invention_structure_prompt(invention_point: dict) -> str:
        return INVENTION_STRUCTURE_PROMPT.format(invention_point_json=_json(invention_point))

    @staticmethod
    def build_search_query_prompt(structure: dict) -> str:
        return SEARCH_QUERY_PROMPT.format(invention_structure_json=_json(structure))

    @staticmethod
    def build_prior_art_similarity_prompt(structure: dict, patents: list[dict]) -> str:
        return PRIOR_ART_SIMILARITY_PROMPT.format(
            invention_structure_json=_json(structure),
            patent_abstracts_json=_json(patents),
        )
