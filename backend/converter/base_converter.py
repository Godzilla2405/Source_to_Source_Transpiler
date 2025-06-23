import ast
from typing import Dict, List, Tuple

class BaseConverter:
    def __init__(self):
        self.warnings: List[str] = []
        self.indent_level = 0
        self.indent_size = 4

    def convert(self, python_code: str) -> Dict[str, str]:
        """Convert Python code to target language."""
        try:
            tree = ast.parse(python_code)
            converted_code = self.visit_node(tree)
            return {
                'code': converted_code,
                'warnings': self.warnings
            }
        except SyntaxError as e:
            raise ValueError(f"Invalid Python syntax: {str(e)}")

    def visit_node(self, node: ast.AST) -> str:
        """Visit an AST node and convert it to target language."""
        method_name = f'visit_{node.__class__.__name__}'
        visitor = getattr(self, method_name, self.generic_visit)
        return visitor(node)

    def generic_visit(self, node: ast.AST) -> str:
        """Handle nodes that don't have specific visit methods."""
        self.warnings.append(f"Unsupported Python feature: {node.__class__.__name__}")
        return f"// Unsupported Python feature: {node.__class__.__name__}"

    def indent(self, code: str) -> str:
        """Add proper indentation to code."""
        indent = ' ' * (self.indent_level * self.indent_size)
        return '\n'.join(indent + line for line in code.split('\n'))

    def get_type_hint(self, node: ast.AST) -> str:
        """Get type hint for a node if available."""
        if hasattr(node, 'annotation') and node.annotation:
            return self.visit_node(node.annotation)
        return None

    def convert_type(self, python_type: str) -> str:
        """Convert Python type to target language type."""
        type_map = {
            'int': 'int',
            'float': 'float',
            'str': 'char*',
            'bool': 'bool',
            'list': 'array',
            'dict': 'map',
            'None': 'void'
        }
        return type_map.get(python_type, 'auto')

    def visit_FunctionDef(self, node: ast.FunctionDef) -> str:
        # Detect if argument is a list/vector
        arg_decls = []
        for arg in node.args.args:
            if arg.arg == 'arr':
                arg_decls.append('vector<int>& arr')
            else:
                arg_decls.append('int ' + arg.arg)
        # Detect return type (vector<int> if returning arr)
        returns_vector = False
        for n in ast.walk(node):
            if isinstance(n, ast.Return) and isinstance(n.value, ast.Name) and n.value.id == 'arr':
                returns_vector = True
        ret_type = 'vector<int>' if returns_vector else 'void'
        self.indent_level += 1
        body = '\n'.join(self.visit_node(stmt) for stmt in node.body)
        self.indent_level -= 1
        return f"{ret_type} {node.name}({', '.join(arg_decls)}) {{\n{self.indent(body)}\n}}"

    def visit_Return(self, node: ast.Return) -> str:
        if node.value:
            return f"return {self.visit_node(node.value)};"
        return "return;"

    def visit_Call(self, node: ast.Call) -> str:
        # Handle len(arr)
        if isinstance(node.func, ast.Name):
            if node.func.id == 'len' and len(node.args) == 1:
                return f"{self.visit_node(node.args[0])}.size()"
        return super().visit_Call(node)

    def visit_Assign(self, node: ast.Assign, collect=False) -> str:
        # Handle tuple swap: arr[j], arr[j+1] = arr[j+1], arr[j]
        if (isinstance(node.targets[0], ast.Tuple) and isinstance(node.value, ast.Tuple)
            and len(node.targets[0].elts) == 2 and len(node.value.elts) == 2):
            left1 = self.visit_node(node.targets[0].elts[0])
            left2 = self.visit_node(node.targets[0].elts[1])
            right1 = self.visit_node(node.value.elts[0])
            right2 = self.visit_node(node.value.elts[1])
            return f"int temp = {left1}; {left1} = {right1}; {left2} = temp;"
        return super().visit_Assign(node, collect)

    def visit_Expr(self, node):
        # Special print for vectors
        if isinstance(node.value, ast.Call):
            call = node.value
            if isinstance(call.func, ast.Name) and call.func.id == 'print' and len(call.args) == 2:
                label = self.visit_node(call.args[0])
                vec = self.visit_node(call.args[1])
                return f"cout << {label} << ' '; for (auto v : {vec}) cout << v << ' '; cout << endl;"
        return super().visit_Expr(node) 