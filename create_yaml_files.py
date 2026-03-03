import os, textwrap

def w(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(textwrap.dedent(content).strip() + '\n')
    print(f"  OK: {path} ({os.path.getsize(path)} bytes)")

# ── 1. knowledge/taxonomy.yaml ──
w('knowledge/taxonomy.yaml', """
    # AI Quantum Solver - Problem Stage Taxonomy
    # Version: 1.0
    # Updated: 2026-03-03

    version: "1.0"

    stages:
      task_generation:
        name_ko: "업무(듀티) 생성"
        name_en: "Task / Duty Generation"
        description: >
          주어진 시간표(운행 계획)에서 법적·운영 제약을 만족하는
          최소 비용의 듀티(근무 단위)를 생성한다.
        formulations:
          - set_covering
          - set_partitioning
          - column_generation
        typical_objectives:
          - min_duties
          - min_total_cost
          - min_deadhead
        required_data:
          - timetable
          - work_regulations
        optional_data:
          - crew_info
          - existing_duty

      shift_scheduling:
        name_ko: "교번(시프트) 편성"
        name_en: "Shift Scheduling"
        description: >
          생성된 듀티를 교번표(시프트 패턴)로 묶어
          근무-휴무 균형과 공정성을 확보한다.
        formulations:
          - integer_programming
          - set_covering
        typical_objectives:
          - min_shifts
          - balance_workload
          - min_overtime
        required_data:
          - duty_set
          - work_regulations
        optional_data:
          - crew_info
          - demand_profile

      roster_assignment:
        name_ko: "로스터(배치) 할당"
        name_en: "Roster Assignment"
        description: >
          교번 또는 듀티를 개별 승무원에게 배정하여
          자격, 선호도, 공정성을 만족시킨다.
        formulations:
          - assignment_problem
          - constraint_satisfaction
          - multi_objective_optimization
        typical_objectives:
          - min_cost
          - max_fairness
          - max_preference_satisfaction
        required_data:
          - duty_set_or_shift_set
          - crew_info
          - work_regulations
        optional_data:
          - preference_data

      realtime_rescheduling:
        name_ko: "실시간 재스케줄링"
        name_en: "Real-time Rescheduling"
        description: >
          운행 중 지연, 결근 등 돌발 상황에서
          기존 스케줄을 최소 변경으로 수정한다.
        formulations:
          - re_optimization
          - constraint_propagation
        typical_objectives:
          - min_deviation_from_original
          - min_uncovered_trips
          - min_delay_propagation
        required_data:
          - current_schedule
          - disruption_info
        optional_data:
          - crew_availability

      integrated:
        name_ko: "통합 스케줄링"
        name_en: "Integrated Scheduling"
        description: >
          듀티 생성 + 로스터 배정 등 복수 단계를
          동시에 최적화한다.
        formulations:
          - decomposition
          - bi_level_optimization
        typical_objectives:
          - min_total_system_cost
          - min_crew_count
        required_data:
          - timetable
          - work_regulations
          - crew_info
        optional_data:
          - demand_profile
          - preference_data
""")

# ── 2. knowledge/data_detection.yaml ──
w('knowledge/data_detection.yaml', """
    # AI Quantum Solver - Data Type Detection Rules
    # Version: 1.0

    version: "1.0"

    data_types:
      timetable:
        name_ko: "시간표 / 운행 계획"
        column_keywords:
          - ["departure", "arrival", "출발", "도착", "dep_time", "arr_time"]
          - ["station", "역", "역명", "정거장"]
          - ["train", "열차", "trip", "운행"]
        structural_hints:
          - "rows represent individual trips or segments"
          - "time columns in HH:MM or minutes format"
        extraction_keys:
          - trip_count
          - station_list
          - direction_count
          - time_range
          - line_count

      work_regulations:
        name_ko: "근무 규정 / 협약"
        column_keywords:
          - ["max_work", "max_drive", "최대근무", "최대승무"]
          - ["break", "휴식", "rest", "식사"]
          - ["overtime", "초과근무", "연장"]
        structural_hints:
          - "parameter-value pairs or key-value table"
          - "contains time durations or limits"
        extraction_keys:
          - max_work_minutes
          - max_driving_minutes
          - min_break_minutes
          - prep_time_minutes
          - cleanup_time_minutes
          - night_rest_minutes

      crew_info:
        name_ko: "승무원 정보"
        column_keywords:
          - ["crew", "승무원", "기관사", "driver", "employee"]
          - ["qualification", "자격", "등급", "grade"]
          - ["base", "소속", "depot", "사업소"]
        structural_hints:
          - "one row per crew member"
          - "contains ID and attribute columns"
        extraction_keys:
          - crew_count
          - qualification_types
          - depot_list

      existing_duty:
        name_ko: "기존 듀티표 / DIA"
        column_keywords:
          - ["duty", "듀티", "DIA", "교번", "근무번호"]
          - ["sequence", "순서", "order"]
          - ["start_time", "end_time", "시작", "종료"]
        structural_hints:
          - "rows represent duty assignments or DIA entries"
          - "may include trip sequences within each duty"
        extraction_keys:
          - duty_count
          - avg_duty_duration
          - duty_types

      demand_profile:
        name_ko: "수요 프로필"
        column_keywords:
          - ["demand", "수요", "passengers", "승객"]
          - ["peak", "첨두", "off_peak", "비첨두"]
          - ["headway", "배차간격", "frequency"]
        structural_hints:
          - "time-indexed demand or frequency data"
        extraction_keys:
          - peak_hours
          - min_headway
          - max_headway

      constraint_document:
        name_ko: "제약조건 문서"
        column_keywords:
          - ["constraint", "제약", "조건", "규칙", "rule"]
        structural_hints:
          - "text-heavy document or structured rules"
          - "may be a PDF or markdown file"
        extraction_keys:
          - constraint_list
          - hard_constraint_count
          - soft_constraint_count
""")

# ── 3. knowledge/matching_rules.yaml ──
w('knowledge/matching_rules.yaml', """
    # AI Quantum Solver - Data-to-Problem Matching Rules
    # Version: 1.0

    version: "1.0"

    rules:
      duty_gen_standard:
        required_data:
          - timetable
          - work_regulations
        optional_data:
          - existing_duty
        recommended_stage: task_generation
        base_confidence: 0.80
        boost_conditions:
          - condition: "existing_duty detected"
            boost: 0.10
            reason: "기존 DIA가 있으면 듀티 재생성 가능성 높음"
          - condition: "trip_count >= 50"
            boost: 0.05
            reason: "대규모 운행은 최적화 필요성 높음"

      roster_standard:
        required_data:
          - duty_set_or_shift_set
          - crew_info
          - work_regulations
        optional_data:
          - preference_data
        recommended_stage: roster_assignment
        base_confidence: 0.75
        boost_conditions:
          - condition: "crew_count >= 20"
            boost: 0.10
          - condition: "preference_data detected"
            boost: 0.05

      shift_sched_standard:
        required_data:
          - duty_set
          - work_regulations
        optional_data:
          - demand_profile
        recommended_stage: shift_scheduling
        base_confidence: 0.70
        boost_conditions:
          - condition: "demand_profile detected"
            boost: 0.15

      integrated_standard:
        required_data:
          - timetable
          - work_regulations
          - crew_info
        optional_data:
          - existing_duty
          - demand_profile
        recommended_stage: integrated
        base_confidence: 0.65
        boost_conditions:
          - condition: "all five data types detected"
            boost: 0.20

      rescheduling:
        required_data:
          - current_schedule
          - disruption_info
        recommended_stage: realtime_rescheduling
        base_confidence: 0.85
""")

# ── 4. knowledge/domains/railway.yaml ──
w('knowledge/domains/railway.yaml', """
    # AI Quantum Solver - Railway Domain Knowledge
    # Version: 1.0

    version: "1.0"
    domain: railway
    name_ko: "철도"
    name_en: "Railway"

    detection_keywords:
      - ["철도", "열차", "train", "railway", "rail"]
      - ["역", "station", "정거장", "터미널"]
      - ["노선", "line", "route", "구간"]
      - ["DIA", "다이아", "운행도표"]
      - ["기관사", "승무원", "차장", "conductor"]

    sub_domains:
      urban_metro:
        name_ko: "도시철도 / 지하철"
        detection_keywords: ["지하철", "도시철도", "metro", "subway", "경전철"]
        characteristics:
          - "high frequency, short headway"
          - "fixed routes with defined termini"
          - "typically bidirectional single-line"

      high_speed:
        name_ko: "고속철도"
        detection_keywords: ["KTX", "고속", "high-speed", "HSR", "SRT"]
        characteristics:
          - "long-distance, fewer stops"
          - "complex crew base assignments"
          - "meal break requirements critical"

      conventional:
        name_ko: "일반 여객철도"
        detection_keywords: ["무궁화", "새마을", "ITX", "일반열차"]
        characteristics:
          - "mixed express and local services"
          - "multi-line crew sharing possible"

      freight:
        name_ko: "화물철도"
        detection_keywords: ["화물", "freight", "cargo", "컨테이너"]
        characteristics:
          - "irregular schedules"
          - "tonnage-based constraints"

    problem_variants:
      duty_generation:
        single_line_bidirectional:
          name_ko: "단일노선 양방향 듀티 생성"
          description: >
            하나의 노선에서 상행/하행 열차를 조합하여
            승무 듀티를 생성한다.
          detection_hints:
            - "exactly 2 termini (e.g., station A and station B)"
            - "direction column with UP/DOWN or 상행/하행"
            - "single line identifier"
          typical_decision_variables:
            - "x[d] = 1 if duty d is selected"
            - "y[t,d] = 1 if trip t is assigned to duty d"
          example_objectives:
            - "minimize total number of duties"
            - "minimize total deadhead time"
            - "minimize total work time"

        single_line_unidirectional:
          name_ko: "단일노선 단방향 듀티 생성"
          description: >
            한 방향만 운행하는 구간의 듀티 생성.
          detection_hints:
            - "trips only in one direction"
            - "crew repositioning required"

        multi_line:
          name_ko: "다중노선 듀티 생성"
          description: >
            여러 노선의 열차를 통합하여 듀티를 생성한다.
          detection_hints:
            - "multiple line identifiers"
            - "3+ termini"
            - "cross-line transfers possible"

        circular_line:
          name_ko: "순환노선 듀티 생성"
          description: >
            순환 노선(예: 환상선)에서의 듀티 생성.
          detection_hints:
            - "no fixed termini"
            - "loop or circular route pattern"

      roster_assignment:
        cyclic_roster:
          name_ko: "순환 로스터 배정"
          description: "교번을 일정 주기로 순환 배정"
        individual_roster:
          name_ko: "개별 로스터 배정"
          description: "개인별 최적 로스터 배정"

    constraints:
      hard:
        trip_coverage:
          name_ko: "운행 커버리지"
          description: "모든 열차 운행은 정확히 하나의 듀티에 배정"
          parameter: null
          formulation: "sum(y[t,d] for d) == 1 for all t"

        max_driving_time:
          name_ko: "최대 승무시간"
          description: "하나의 듀티에서 실제 운전(승무) 시간 상한"
          parameter: max_driving_minutes
          unit: minutes
          typical_range: [240, 420]
          formulation: "driving_time[d] <= max_driving_minutes"

        max_work_time:
          name_ko: "최대 근무시간"
          description: "준비-승무-정리를 포함한 총 근무시간 상한"
          parameter: max_work_minutes
          unit: minutes
          typical_range: [480, 720]
          formulation: "work_time[d] <= max_work_minutes"

        mandatory_break:
          name_ko: "필수 휴식"
          description: "연속 승무 후 최소 식사·휴식 시간"
          parameter: min_break_minutes
          unit: minutes
          typical_range: [30, 60]
          formulation: "break_time[d] >= min_break_minutes if continuous_drive > threshold"

        night_rest:
          name_ko: "야간 휴식"
          description: "야간 근무 후 최소 연속 휴식"
          parameter: night_rest_minutes
          unit: minutes
          typical_range: [240, 480]

        prep_cleanup:
          name_ko: "준비/정리 시간"
          description: "근무 시작 전 준비, 종료 후 정리 시간"
          parameters:
            prep_time_minutes:
              typical_range: [20, 60]
            cleanup_time_minutes:
              typical_range: [20, 60]

        qualification:
          name_ko: "자격 요건"
          description: "승무원 자격이 해당 노선/열차 요건과 일치"
          parameter: null
          formulation: "assign only if crew qualifies for the line/train type"

      soft:
        workload_balance:
          name_ko: "업무량 균형"
          description: "듀티 간 근무시간 편차 최소화"
          weight_range: [0.1, 1.0]

        minimize_deadhead:
          name_ko: "공차회송 최소화"
          description: "비운행 이동(회송) 시간 최소화"
          weight_range: [0.1, 1.0]

        minimize_split_duties:
          name_ko: "분리근무 최소화"
          description: "중간에 긴 대기가 있는 분리근무 최소화"
          weight_range: [0.1, 0.5]

        depot_proximity:
          name_ko: "사업소 근접성"
          description: "근무 시작/종료지가 소속 사업소에 가까울수록 유리"
          weight_range: [0.05, 0.3]

        preference_satisfaction:
          name_ko: "선호도 반영"
          description: "승무원의 근무 선호를 가능한 반영"
          weight_range: [0.05, 0.2]

    reference_values:
      korean_urban_rail:
        max_driving_minutes: 360
        max_work_minutes: 660
        prep_time_minutes: 40
        cleanup_time_minutes: 40
        min_break_minutes: 40
        night_rest_minutes: 360
        typical_duty_count_range: [30, 80]
      korean_conventional_rail:
        max_driving_minutes: 420
        max_work_minutes: 720
        prep_time_minutes: 60
        cleanup_time_minutes: 60
        min_break_minutes: 45
        night_rest_minutes: 480
""")

# ── 5. prompts/problem_definition.yaml ──
w('prompts/problem_definition.yaml', """
    # AI Quantum Solver - Problem Definition Prompt
    # Version: 1.0
    # Used by: ProblemDefinitionSkill

    version: "1.0"

    system_prompt: |
      You are an optimization problem definition expert.
      Your role is to analyze uploaded data and recommend the most
      appropriate optimization problem formulation.

      Rules:
      1. Always base recommendations on detected data characteristics.
      2. Use the taxonomy from knowledge/taxonomy.yaml.
      3. Use domain-specific knowledge from knowledge/domains/*.yaml.
      4. Never hard-code numeric values - extract from data.
      5. Present recommendations with confidence scores.
      6. Ask clarification questions when confidence < 0.7.

    conversation_flow:
      step_1_data_recognition:
        trigger: "analysis_completed AND NOT problem_defined"
        action: "Summarize detected data types and key statistics"
        template: |
          ## Data Analysis Summary

          Detected data types:
          {detected_data_summary}

          Key statistics:
          {key_statistics}

      step_2_domain_detection:
        action: "Identify domain from data keywords"
        template: |
          ## Domain Detection

          Detected domain: {domain_name}
          Confidence: {domain_confidence}
          Evidence: {domain_evidence}

      step_3_problem_recommendation:
        action: "Match data to problem type using matching rules"
        template: |
          ## Recommended Problem Definition

          **Problem Type**: {problem_stage} - {problem_variant}
          **Confidence**: {confidence}

          **Objective Function**:
          {objectives}

          **Hard Constraints**:
          {hard_constraints}

          **Soft Constraints (optional)**:
          {soft_constraints}

          **Required Parameters** (to be collected from user):
          {required_parameters}

      step_4_clarification:
        condition: "confidence < 0.7 OR ambiguous data"
        questions:
          - "Which problem would you like to solve: {option_a} or {option_b}?"
          - "What is the primary objective: minimize cost, minimize crew count, or balanced?"
          - "Are there additional constraints not found in the data?"
          - "Is this for a single line or multiple lines?"

      step_5_confirmation:
        action: "Present final problem definition for user confirmation"
        template: |
          ## Problem Definition Confirmation

          {final_problem_summary}

          Do you confirm this problem definition?
          Type 'confirm' or suggest modifications.

    confirmation_keywords:
      positive: ["confirm", "ok", "yes", "approve",
                  "확인", "네", "좋습니다", "승인", "진행"]
      modify: ["modify", "change", "adjust",
               "수정", "변경", "조정"]
      restart: ["restart", "reset", "다시",
                "재시작", "처음부터"]

    response_format:
      language: "user_language"
      style: "structured_markdown"
      include_confidence: true
      include_evidence: true
""")

print("\n=== All files created successfully ===")
print("\nDirectory structure:")
for root, dirs, files in os.walk('knowledge'):
    level = root.replace('knowledge', '').count(os.sep)
    indent = '  ' * level
    print(f"{'knowledge/' if level == 0 else indent + os.path.basename(root) + '/'}")
    for f in files:
        fpath = os.path.join(root, f)
        print(f"  {indent}{f} ({os.path.getsize(fpath)} bytes)")

print()
for root, dirs, files in os.walk('prompts'):
    level = root.replace('prompts', '').count(os.sep)
    indent = '  ' * level
    print(f"{'prompts/' if level == 0 else indent + os.path.basename(root) + '/'}")
    for f in files:
        fpath = os.path.join(root, f)
        print(f"  {indent}{f} ({os.path.getsize(fpath)} bytes)")