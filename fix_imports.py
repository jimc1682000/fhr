#!/usr/bin/env python3
"""Quick script to fix import sorting issues in Python files."""
import os
import re
from pathlib import Path


def fix_imports_in_file(filepath):
    """Fix import sorting in a single Python file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    lines = content.split('\n')
    
    # Find import blocks
    i = 0
    while i < len(lines):
        # Skip shebang and module docstrings
        if i == 0 and lines[i].startswith('#!'):
            i += 1
            continue
        if i < len(lines) and (lines[i].startswith('"""') or lines[i].startswith("'''")):
            # Skip docstring
            if lines[i].count('"""') == 1 or lines[i].count("'''") == 1:
                i += 1
                quote = '"""' if '"""' in lines[i-1] else "'''"
                while i < len(lines) and quote not in lines[i]:
                    i += 1
            i += 1
            continue
            
        # Check if we're at the start of imports
        if lines[i].startswith('import ') or lines[i].startswith('from '):
            import_start = i
            import_lines = []
            
            # Collect all consecutive import lines
            while i < len(lines) and (lines[i].startswith('import ') or 
                                      lines[i].startswith('from ') or 
                                      lines[i].strip() == ''):
                if lines[i].strip():
                    import_lines.append(lines[i])
                i += 1
            
            if import_lines:
                # Sort imports: stdlib first, then third-party, then local
                stdlib_imports = []
                third_party_imports = []
                local_imports = []
                
                for line in import_lines:
                    if line.startswith('from '):
                        module = line.split()[1].split('.')[0]
                    else:
                        module = line.split()[1].split('.')[0].rstrip(',')
                    
                    # Common stdlib modules
                    if module in ['os', 'sys', 'json', 'unittest', 'tempfile', 
                                  'datetime', 'pathlib', 'argparse', 're', 'trace',
                                  'io', 'uuid', 'shutil', 'logging', 'typing',
                                  'contextlib', 'asyncio']:
                        stdlib_imports.append(line)
                    elif module in ['attendance_analyzer', 'lib', 'server']:
                        local_imports.append(line)
                    else:
                        third_party_imports.append(line)
                
                # Sort each group
                stdlib_imports.sort()
                third_party_imports.sort()
                local_imports.sort()
                
                # Reconstruct the import block
                new_imports = []
                if stdlib_imports:
                    new_imports.extend(stdlib_imports)
                if third_party_imports:
                    if new_imports:
                        new_imports.append('')
                    new_imports.extend(third_party_imports)
                if local_imports:
                    if new_imports:
                        new_imports.append('')
                    new_imports.extend(local_imports)
                
                # Replace in original lines
                lines[import_start:i] = new_imports + ['']
                
                # Update content
                content = '\n'.join(lines)
                
                # Write back
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                return True
        
        i += 1
    
    return False


def main():
    """Fix imports in all Python files."""
    fixed_count = 0
    
    # Fix test files
    test_dir = Path('test')
    for py_file in test_dir.glob('*.py'):
        if fix_imports_in_file(py_file):
            print(f"Fixed imports in {py_file}")
            fixed_count += 1
    
    # Fix lib files
    lib_dir = Path('lib')
    for py_file in lib_dir.glob('*.py'):
        if fix_imports_in_file(py_file):
            print(f"Fixed imports in {py_file}")
            fixed_count += 1
    
    # Fix server files
    server_dir = Path('server')
    if server_dir.exists():
        for py_file in server_dir.glob('*.py'):
            # Skip server/main.py as we've already fixed it manually
            if py_file.name != 'main.py' and fix_imports_in_file(py_file):
                print(f"Fixed imports in {py_file}")
                fixed_count += 1
    
    print(f"\nFixed {fixed_count} files")


if __name__ == '__main__':
    main()