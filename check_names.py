import ast

def check_undefined_names(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        tree = ast.parse(f.read())

    defined_names = set()
    used_names = set()

    # Simple tracker for defined names (imports and functions)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for name in node.names:
                defined_names.add(name.asname or name.name.split('.')[0])
        elif isinstance(node, ast.FunctionDef):
            defined_names.add(node.name)
            # Add arguments to defined names within the function scope
            for arg in node.args.args:
                defined_names.add(arg.arg)
        elif isinstance(node, ast.ClassDef):
            defined_names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    defined_names.add(target.id)

    # Tracker for used names
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used_names.add(node.id)

    # Common built-ins to ignore
    builtins = {'print', 'len', 'range', 'str', 'int', 'float', 'list', 'dict', 'set', 'bool', 'Exception', 'ImportError', 'isinstance', 'type', 'getattr', 'hasattr', 'any', 'all', 'sorted', 'min', 'max', 'sum', 'iter', 'next', 'dir', 'vars', 'ValueError', 'TypeError', 'AttributeError', 'NameError', 'StopIteration', 'True', 'False', 'None'}
    
    undefined = used_names - defined_names - builtins
    return undefined

undefined = check_undefined_names('graphic_renderer.py')
print(f"Undefined names found: {undefined}")
