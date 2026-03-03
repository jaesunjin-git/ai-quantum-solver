import ast

# ── 1. core/models.py에 컬럼 추가 ──
with open('core/models.py', 'r', encoding='utf-8') as f:
    content = f.read()

# SessionStateDB의 기존 컬럼 확인
print('=== models.py: SessionStateDB columns ===')
in_class = False
last_column_line = 0
lines = content.split('\n')
for i, line in enumerate(lines):
    if 'class SessionStateDB' in line:
        in_class = True
    if in_class:
        if 'Column(' in line:
            last_column_line = i
            print(f'  {i+1:4d}| {line.strip()}')
        if in_class and line.strip().startswith('class ') and 'SessionStateDB' not in line:
            break

print(f'\n  Last column at line {last_column_line + 1}')

# data_facts 컬럼 뒤에 problem_defined 관련 컬럼 추가
new_columns = '''
    # Problem Definition
    problem_defined = Column(Boolean, default=False)
    problem_definition = Column(Text, nullable=True)
    confirmed_problem = Column(Text, nullable=True)
'''

if 'problem_defined' not in content:
    # data_facts 컬럼 뒤에 삽입
    if 'data_facts' in content and 'Column' in content.split('data_facts')[1].split('\n')[0]:
        content = content.replace(
            'data_facts = Column(',
            'data_facts = Column('
        )
        # find the data_facts line and insert after
        lines = content.split('\n')
        new_lines = []
        inserted = False
        for i, line in enumerate(lines):
            new_lines.append(line)
            if not inserted and 'data_facts' in line and 'Column(' in line:
                new_lines.append('')
                new_lines.append('    # Problem Definition')
                new_lines.append('    problem_defined = Column(Boolean, default=False)')
                new_lines.append('    problem_definition = Column(Text, nullable=True)')
                new_lines.append('    confirmed_problem = Column(Text, nullable=True)')
                inserted = True
                print(f'  Inserted after line {i+1}')
        if not inserted:
            # fallback: insert after last column
            new_lines = []
            for i, line in enumerate(lines):
                new_lines.append(line)
                if i == last_column_line:
                    new_lines.append('')
                    new_lines.append('    # Problem Definition')
                    new_lines.append('    problem_defined = Column(Boolean, default=False)')
                    new_lines.append('    problem_definition = Column(Text, nullable=True)')
                    new_lines.append('    confirmed_problem = Column(Text, nullable=True)')
                    inserted = True
                    print(f'  Inserted after line {i+1} (fallback)')
        content = '\n'.join(new_lines)
        with open('core/models.py', 'w', encoding='utf-8') as f:
            f.write(content)
        print(f'  models.py updated ({len(content)} bytes)')
else:
    print('  models.py: already has problem_defined')

# ── 2. agent.py: PROBLEM_DEFINITION handler 확인/추가 ──
with open('domains/crew/agent.py', 'r', encoding='utf-8') as f:
    content = f.read()

print('\n=== agent.py: _execute_skill handlers ===')
lines = content.split('\n')
for i, line in enumerate(lines):
    if i >= 310 and i <= 330:
        print(f'  {i+1:4d}| {line}')

# Check if PROBLEM_DEFINITION is in the handlers dict
handler_section = content.split('handlers = {')[1].split('}')[0] if 'handlers = {' in content else ''
if 'PROBLEM_DEFINITION' not in handler_section:
    content = content.replace(
        '"ANALYZE": lambda s, p, m, pr: skill_analyze(self.model, s, p, m, pr),',
        '"ANALYZE": lambda s, p, m, pr: skill_analyze(self.model, s, p, m, pr),\n            "PROBLEM_DEFINITION": lambda s, p, m, pr: skill_problem_definition(self.model, s, p, m, pr),'
    )
    with open('domains/crew/agent.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('  PROBLEM_DEFINITION handler ADDED')
else:
    print('  PROBLEM_DEFINITION handler already exists')

# ── 3. Syntax check ──
print('\n=== Syntax Check ===')
for f in ['core/models.py', 'domains/crew/agent.py']:
    with open(f, 'r', encoding='utf-8') as fh:
        src = fh.read()
    try:
        ast.parse(src)
        print(f'  PASS: {f}')
    except SyntaxError as e:
        print(f'  FAIL: {f} - line {e.lineno}: {e.msg}')
        sl = src.split('\n')
        for j in range(max(0, e.lineno-3), min(len(sl), e.lineno+3)):
            print(f'    {j+1:3d}| {sl[j]}')

# ── 4. DB 마이그레이션 안내 ──
print('\n=== DB Migration Required ===')
print('  새 컬럼이 추가되었으므로 DB 테이블을 업데이트해야 합니다.')
print('  옵션 1: reset_db.py 실행 (데이터 초기화)')
print('  옵션 2: ALTER TABLE 수동 실행')