import sys
sys.path.insert(0, '.')

from core.database import engine
from sqlalchemy import text, inspect

# 현재 테이블 컬럼 확인
insp = inspect(engine)
try:
    columns = [c['name'] for c in insp.get_columns('session_states', schema='core')]
    print(f'Current columns: {columns}')
except Exception as e:
    print(f'Error inspecting: {e}')
    columns = []

# 필요한 컬럼 추가
new_cols = {
    'problem_defined': 'BOOLEAN DEFAULT FALSE',
    'problem_definition': 'TEXT',
    'confirmed_problem': 'TEXT',
}

with engine.connect() as conn:
    for col_name, col_type in new_cols.items():
        if col_name not in columns:
            try:
                conn.execute(text(f'ALTER TABLE core.session_states ADD COLUMN {col_name} {col_type}'))
                conn.commit()
                print(f'  ADDED: {col_name}')
            except Exception as e:
                err = str(e)
                if 'already exists' in err or 'duplicate' in err.lower():
                    print(f'  EXISTS: {col_name}')
                else:
                    print(f'  ERROR: {col_name} - {e}')
        else:
            print(f'  EXISTS: {col_name}')

# 확인
columns2 = [c['name'] for c in insp.get_columns('session_states', schema='core')]
print(f'\nFinal columns: {columns2}')