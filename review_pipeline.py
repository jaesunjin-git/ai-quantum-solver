import os

# 전체 파이프라인 관련 파일들의 핵심 부분만 추출
files_to_check = {
    'engine/math_model_generator.py': ['def ', 'class ', 'async def ', 'gate', 'profile', 'data_facts', 'csv_summary'],
    'engine/pre_decision.py': ['def ', 'class ', 'async def ', 'math_model', 'solver'],
    'domains/crew/skills/math_model.py': ['def ', 'class ', 'async def ', 'gate', 'session', 'analysis'],
    'domains/crew/skills/handlers.py': ['def ', 'class ', 'async def '],
    'engine/gates/gate2_model_validate.py': ['def ', 'class ', 'validation', 'error'],
}

for filepath, keywords in files_to_check.items():
    if not os.path.exists(filepath):
        print(f'\n===== NOT FOUND: {filepath} =====')
        continue
    
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        lines = f.readlines()
    
    size = os.path.getsize(filepath)
    print(f'\n===== {filepath} ({size:,} bytes, {len(lines)} lines) =====')
    
    # 함수/클래스 목록 + 핵심 로직 라인
    for i, line in enumerate(lines):
        stripped = line.strip()
        if any(kw in stripped for kw in keywords):
            if len(stripped) > 5 and not stripped.startswith('#'):
                print(f'  {i+1:4d}| {stripped[:120]}')