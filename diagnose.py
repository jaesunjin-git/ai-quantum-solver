import ast

# 1. agent.py에서 가드 위치와 순서 확인
with open('domains/crew/agent.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print('=== agent.py: Guard & Routing Order ===')
for i, line in enumerate(lines):
    stripped = line.strip()
    if any(kw in stripped for kw in [
        'analysis_completed', 'problem_defined', 'pre_decision_done',
        'PROBLEM_DEFINITION', '_execute_skill', 'quick_intent',
        'Phase1', 'Phase'
    ]):
        print(f'  {i+1:4d}| {stripped[:120]}')

# 2. session.py에서 problem_defined 초기값과 DB 컬럼 확인
print()
print('=== session.py: problem_defined field ===')
with open('domains/crew/session.py', 'r', encoding='utf-8') as f:
    content = f.read()

for keyword in ['problem_defined', 'problem_definition_proposed', 'confirmed_problem']:
    count = content.count(keyword)
    print(f'  {keyword}: {count} occurrences')

# 3. DB 모델 확인 - SessionStateDB에 problem_defined 컬럼이 있는지
print()
print('=== core/models.py: SessionStateDB columns ===')
with open('core/models.py', 'r', encoding='utf-8') as f:
    models_content = f.read()

if 'problem_defined' in models_content:
    print('  OK: problem_defined column exists')
else:
    print('  MISSING: problem_defined column NOT in models.py')
    # show SessionStateDB class
    in_class = False
    for line in models_content.split('\n'):
        if 'class SessionStateDB' in line:
            in_class = True
        if in_class:
            print(f'    {line}')
            if line.strip() == '' and in_class:
                break

# 4. problem_definition.py 시그니처 확인
print()
print('=== problem_definition.py: function signature ===')
with open('domains/crew/skills/problem_definition.py', 'r', encoding='utf-8') as f:
    for line in f:
        if 'async def skill_problem_definition' in line:
            print(f'  {line.strip()}')
        if 'async def handle' in line:
            print(f'  {line.strip()}')

# 5. agent.py handler 등록 확인
print()
print('=== agent.py: handler registration ===')
with open('domains/crew/agent.py', 'r', encoding='utf-8') as f:
    for i, line in enumerate(f, 1):
        if 'PROBLEM_DEFINITION' in line:
            print(f'  {i:4d}| {line.rstrip()}')