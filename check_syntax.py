import ast
import sys

files = [
    r'C:\Users\User\1c-syntax-helper-mcp\.worktrees\sse-fix\src\main.py',
    r'C:\Users\User\1c-syntax-helper-mcp\.worktrees\sse-fix\src\core\lifespan.py',
    r'C:\Users\User\1c-syntax-helper-mcp\.worktrees\sse-fix\src\routes\mcp_routes.py',
    r'C:\Users\User\1c-syntax-helper-mcp\.worktrees\sse-fix\src\core\constants.py'
]

print("Проверка синтаксиса Python файлов:\n")
print("=" * 80)

all_ok = True

for filepath in files:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        ast.parse(source)
        print(f'✓ {filepath}: OK')
    except SyntaxError as e:
        print(f'✗ {filepath}: SYNTAX ERROR - {e.msg} (line {e.lineno}, col {e.offset})')
        all_ok = False
    except FileNotFoundError:
        print(f'✗ {filepath}: FILE NOT FOUND')
        all_ok = False
    except Exception as e:
        print(f'✗ {filepath}: ERROR - {type(e).__name__}: {e}')
        all_ok = False

print("=" * 80)
print(f"\nРезультат: {'Все файлы корректны' if all_ok else 'Обнаружены ошибки'}")
sys.exit(0 if all_ok else 1)
