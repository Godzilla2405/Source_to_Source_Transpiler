import ast
from typing import Dict, List

class GeneralPythonToCLikeConverter:
    def __init__(self):
        self.warnings: List[str] = []
        self.indent_level = 0
        self.indent_size = 4
        self.declared_vars = {}
        self.top_level_code = []
        self.includes = set()
        self.language = 'c-like'

    def convert(self, python_code: str) -> Dict[str, str]:
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
        method_name = f'visit_{node.__class__.__name__}'
        visitor = getattr(self, method_name, self.generic_visit)
        return visitor(node)

    def generic_visit(self, node: ast.AST) -> str:
        self.warnings.append(f"Unsupported Python feature: {node.__class__.__name__}")
        return f"// Unsupported Python feature: {node.__class__.__name__}"

    def indent(self, code: str) -> str:
        indent = ' ' * (self.indent_level * self.indent_size)
        return '\n'.join(indent + line for line in code.split('\n'))

    # --- Basic Types and Variables ---
    def visit_Module(self, node: ast.Module) -> str:
        self.declared_vars = {}
        self.top_level_code = []
        body_lines = []
        for stmt in node.body:
            code = self.visit_node(stmt)
            if code:
                body_lines.append(code)
        includes = '\n'.join(f'#include {include}' for include in sorted(self.includes))
        return f"{includes}\n\n" + '\n'.join(body_lines)

    def visit_Expr(self, node: ast.Expr) -> str:
        return self.visit_node(node.value)

    def visit_Assign(self, node: ast.Assign) -> str:
        # Only handle single assignment for now
        if len(node.targets) != 1:
            self.warnings.append("Multiple assignment not supported")
            return "// Multiple assignment not supported"
        target = node.targets[0]
        value = self.visit_node(node.value)
        vtype = self.infer_type(node.value)
        if isinstance(target, ast.Name):
            if target.id not in self.declared_vars:
                self.declared_vars[target.id] = vtype
                return f"{vtype} {target.id} = {value};"
            else:
                return f"{target.id} = {value};"
        self.warnings.append("Complex assignment not supported")
        return "// Complex assignment not supported"

    def visit_Constant(self, node: ast.Constant) -> str:
        if isinstance(node.value, str):
            return f'"{node.value}"'
        elif isinstance(node.value, bool):
            return 'true' if node.value else 'false'
        elif node.value is None:
            return 'nullptr'
        return str(node.value)

    def infer_type(self, value):
        if isinstance(value, ast.Constant):
            if isinstance(value.value, int):
                return 'int'
            elif isinstance(value.value, float):
                return 'double'
            elif isinstance(value.value, str):
                return 'string'
            elif isinstance(value.value, bool):
                return 'bool'
            elif value.value is None:
                return 'void'
        elif isinstance(value, ast.List):
            if value.elts:
                elem_type = self.infer_type(value.elts[0])
                return f'vector<{elem_type}>'
            return 'vector<auto>'
        elif isinstance(value, ast.Dict):
            if value.keys and value.values:
                key_type = self.infer_type(value.keys[0])
                val_type = self.infer_type(value.values[0])
                return f'unordered_map<{key_type}, {val_type}>'
            return 'unordered_map<auto, auto>'
        return 'auto'

    # --- Collections ---
    def visit_List(self, node: ast.List) -> str:
        if not node.elts:
            return "vector<auto>{}"
        elements = [self.visit_node(elt) for elt in node.elts]
        element_type = self.infer_type(node.elts[0])
        return f"vector<{element_type}>{{{', '.join(elements)}}}"

    def visit_Tuple(self, node: ast.Tuple) -> str:
        elements = [self.visit_node(elt) for elt in node.elts]
        return f"make_tuple({', '.join(elements)})"

    def visit_Set(self, node: ast.Set) -> str:
        elements = [self.visit_node(elt) for elt in node.elts]
        return f"unordered_set<auto>{{{', '.join(elements)}}}"

    def visit_Dict(self, node: ast.Dict) -> str:
        if not node.keys:
            return "unordered_map<auto, auto>{}"
        pairs = []
        for key, value in zip(node.keys, node.values):
            key_str = self.visit_node(key)
            value_str = self.visit_node(value)
            pairs.append(f"{{{key_str}, {value_str}}}")
        key_type = self.infer_type(node.keys[0])
        val_type = self.infer_type(node.values[0])
        return f"unordered_map<{key_type}, {val_type}>{{{', '.join(pairs)}}}"

    # --- Control Structures ---
    def visit_If(self, node: ast.If) -> str:
        self.indent_level += 1
        condition = self.visit_node(node.test)
        body = '\n'.join(self.visit_node(stmt) for stmt in node.body)
        else_body = ""
        if node.orelse:
            else_body = " else {\n" + self.indent('\n'.join(self.visit_node(stmt) for stmt in node.orelse)) + "\n}"
        self.indent_level -= 1
        return f"if ({condition}) {{\n{self.indent(body)}\n}}{else_body}"

    def visit_For(self, node: ast.For) -> str:
        self.indent_level += 1
        # Only handle range for now
        if isinstance(node.iter, ast.Call) and isinstance(node.iter.func, ast.Name) and node.iter.func.id == 'range':
            args = node.iter.args
            if len(args) == 1:
                end = self.visit_node(args[0])
                body = '\n'.join(self.visit_node(stmt) for stmt in node.body)
                self.indent_level -= 1
                return f"for (int {node.target.id} = 0; {node.target.id} < {end}; {node.target.id}++) {{\n{self.indent(body)}\n}}"
            elif len(args) == 2:
                start = self.visit_node(args[0])
                end = self.visit_node(args[1])
                body = '\n'.join(self.visit_node(stmt) for stmt in node.body)
                self.indent_level -= 1
                return f"for (int {node.target.id} = {start}; {node.target.id} < {end}; {node.target.id}++) {{\n{self.indent(body)}\n}}"
        self.warnings.append("Only range() based for loops are supported")
        return "// Unsupported for loop type"

    def visit_While(self, node: ast.While) -> str:
        self.indent_level += 1
        condition = self.visit_node(node.test)
        body = '\n'.join(self.visit_node(stmt) for stmt in node.body)
        self.indent_level -= 1
        return f"while ({condition}) {{\n{self.indent(body)}\n}}"

    # --- Functions ---
    def visit_FunctionDef(self, node: ast.FunctionDef) -> str:
        self.indent_level += 1
        args = []
        for arg in node.args.args:
            arg_type = self.infer_type(arg) or 'int'  # Default to int if can't infer
            args.append(f"{arg_type} {arg.arg}")
        body = '\n'.join(self.visit_node(stmt) for stmt in node.body)
        self.indent_level -= 1
        return_type = self.infer_return_type(node) or 'int'  # Default to int if can't infer
        return f"{return_type} {node.name}({', '.join(args)}) {{\n{self.indent(body)}\n}}"

    def visit_Return(self, node: ast.Return) -> str:
        if node.value:
            return f"return {self.visit_node(node.value)};"
        return "return;"

    def visit_Lambda(self, node: ast.Lambda) -> str:
        self.warnings.append("Lambda functions are not supported, use a regular function instead.")
        return "// Lambda functions not supported"

    # --- Classes and OOP ---
    def visit_ClassDef(self, node: ast.ClassDef) -> str:
        self.indent_level += 1
        body = []
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                body.append(self.visit_FunctionDef(item))
        self.indent_level -= 1
        return f"class {node.name} {{\n{self.indent('public:')}\n{self.indent('\n'.join(body))}\n}};"

    # --- File Operations, Exception Handling, Comprehensions, Generators, Decorators, Modules, etc. ---
    def visit_With(self, node: ast.With) -> str:
        self.warnings.append("With/context manager statements are not supported.")
        return "// With/context manager not supported"

    def visit_Try(self, node: ast.Try) -> str:
        self.warnings.append("Try/except/finally statements are not supported.")
        return "// Try/except/finally not supported"

    def visit_ListComp(self, node: ast.ListComp) -> str:
        self.warnings.append("List comprehensions are not supported, use a loop instead.")
        return "// List comprehension not supported"

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> str:
        self.warnings.append("Generator expressions are not supported, use a loop instead.")
        return "// Generator expression not supported"

    def visit_DictComp(self, node: ast.DictComp) -> str:
        self.warnings.append("Dict comprehensions are not supported, use a loop instead.")
        return "// Dict comprehension not supported"

    def visit_Import(self, node: ast.Import) -> str:
        self.warnings.append("Import statements are not supported.")
        return "// Import not supported"

    def visit_ImportFrom(self, node: ast.ImportFrom) -> str:
        self.warnings.append("Import-from statements are not supported.")
        return "// Import-from not supported"

    def visit_Decorator(self, node: ast.AST) -> str:
        self.warnings.append("Decorators are not supported.")
        return "// Decorator not supported"

    # --- Add more as needed for other features --- 