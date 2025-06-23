import ast
from typing import Dict, List

class PythonToCConverter:
    def __init__(self):
        self.warnings: List[str] = []
        self.indent_level = 0
        self.indent_size = 4
        self.declared_vars = {}
        self.top_level_code = []
        self.includes = set([
            '<stdio.h>',
            '<stdlib.h>',
            '<stdbool.h>',
            '<string.h>',
            '<stdint.h>',
            '<float.h>',
            '<math.h>'
        ])
        self.current_function = None
        self.return_type = 'void'
        self.is_generated_main = False
        self.struct_members = {}
        self.has_main = False

    def convert(self, python_code: str) -> Dict[str, str]:
        try:
            tree = ast.parse(python_code)
            converted_code = self.visit(tree) # Use self.visit for the root node
            return {
                'code': converted_code,
                'warnings': self.warnings
            }
        except SyntaxError as e:
            raise ValueError(f"Invalid Python syntax: {str(e)}")

    def visit(self, node):
        """Visit a node."""
        if node is None:
            return ""
            
        method = 'visit_' + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)
        return visitor(node)
        
    def generic_visit(self, node):
        """Called if no explicit visitor function exists for a node."""
        self.warnings.append(f"Unsupported Python feature: {type(node).__name__}")
        return f"// Unsupported Python feature: {type(node).__name__}"

    def indent(self, code: str) -> str:
        if isinstance(code, list):
            code = '\n'.join(code)
        indent = ' ' * (self.indent_level * self.indent_size)
        return '\n'.join(indent + line for line in code.splitlines())

    def visit_Module(self, node: ast.Module) -> str:
        """Convert Python module to C."""
        # Check if printf is needed
        needs_stdio = False
        for item in ast.walk(node):
            if isinstance(item, ast.Call) and isinstance(item.func, ast.Name) and item.func.id == 'print':
                needs_stdio = True
                break

        # Start with necessary includes
        includes = []
        if needs_stdio:
            includes.append('#include <stdio.h>')
        includes.append('#include <stdlib.h>')
        includes.append('#include <string.h>')
        
        # Convert all functions
        func_defs = []
        top_level_statements = [] # To collect statements not in functions
        has_explicit_main = False

        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                if item.name == 'main':
                    has_explicit_main = True
                func_defs.append(self.visit(item))
            else:
                top_level_statements.append(item)

        # If no explicit main, wrap top-level statements in a generated main
        if not has_explicit_main and top_level_statements:
            main_body_stmts = [self.visit(stmt) for stmt in top_level_statements]
            # Ensure main has a return 0 if no explicit return
            if not any(isinstance(n, ast.Return) for n in top_level_statements):
                main_body_stmts.append("return 0;")
            
            main_func = f"int main() {{\n{self.indent('\n'.join(main_body_stmts))}\n}}"
            func_defs.append(main_func)
        elif not has_explicit_main and not top_level_statements:
            # If no explicit main and no top-level statements, generate an empty main
            func_defs.append("int main() {\n    return 0;\n}")

        # Combine includes and function definitions
        return '\n'.join(includes) + '\n\n' + '\n\n'.join(func_defs)

    def _infer_types_in_body(self, body_nodes):
        """Helper to infer types of variables within a function body (first pass)."""
        for node in body_nodes:
            if isinstance(node, ast.Assign):
                if isinstance(node.targets[0], ast.Name):
                    var_name = node.targets[0].id
                    inferred_type = self.infer_type(node.value)
                    self.declared_vars[var_name] = inferred_type
            elif isinstance(node, ast.AugAssign):
                if isinstance(node.target, ast.Name):
                    var_name = node.target.id
                    inferred_type = self.infer_type(node.value)
                    if var_name not in self.declared_vars:
                         self.declared_vars[var_name] = inferred_type
            elif isinstance(node, (ast.For, ast.If, ast.While)):
                # Recursively infer types in nested blocks
                if hasattr(node, 'body'):
                    self._infer_types_in_body(node.body)
                if hasattr(node, 'orelse'): # For If statements
                    self._infer_types_in_body(node.orelse)
            # When infer_type is called from other visit methods, it will use the
            # self.declared_vars populated by this pass.

    def visit_Expr(self, node):
        """Convert Python expression to C."""
        return self.visit(node.value)
        
    def visit_Constant(self, node):
        """Convert Python constant to C."""
        if isinstance(node.value, str):
            return f'"{node.value}"'
        elif isinstance(node.value, bool):
            return "1" if node.value else "0"
        elif node.value is None:
            return "NULL"
        return str(node.value)
        
    def visit_Name(self, node):
        """Convert Python name to C."""
        return node.id

    def visit_FunctionDef(self, node):
        """Convert Python function definition to C."""
        self.current_function = node.name
        
        # Temporarily store original declared_vars, then clear for function scope
        original_declared_vars = self.declared_vars.copy() 
        self.declared_vars = {}

        # First pass: Pre-analyze arguments to infer types based on usage within the function body
        inferred_arg_types = {}
        for arg in node.args.args:
            arg_name = arg.arg
            inferred_type = 'int'
            # Use type hint if present
            if arg.annotation:
                inferred_type = self.get_type(arg.annotation)
            else:
                # Infer from usage in body
                for subnode in ast.walk(ast.Module(body=node.body)):
                    # Used as array (subscripted)
                    if (isinstance(subnode, ast.Subscript) and
                        isinstance(subnode.value, ast.Name) and
                        subnode.value.id == arg_name):
                        # Check if the array is used as a string (e.g., in string functions)
                        is_string = False
                        for call in ast.walk(ast.Module(body=node.body)):
                            if (isinstance(call, ast.Call) and
                                isinstance(call.func, ast.Name) and
                                call.func.id in ['strcat', 'strdup', 'strlen']):
                                for call_arg in call.args:
                                    if (isinstance(call_arg, ast.Name) and call_arg.id == arg_name):
                                        is_string = True
                        if is_string:
                            inferred_type = 'char*'
                        else:
                            inferred_type = 'int*'
            inferred_arg_types[arg_name] = inferred_type
            self.declared_vars[arg_name] = inferred_type

        # Process parameters for C function signature
        params = []
        for arg in node.args.args:
            arg_name = arg.arg
            param_type = inferred_arg_types[arg_name]
            params.append(f"{param_type} {arg_name}")
            if param_type.endswith('*'):
                params.append(f"int {arg_name}_size")
                self.declared_vars[f"{arg_name}_size"] = "int"

        # Determine return type 
        return_type = "void"
        return_stmts = [n for n in ast.walk(ast.Module(body=node.body)) if isinstance(n, ast.Return)]
        if return_stmts:
            first_return_value = return_stmts[0].value
            if first_return_value:
                return_type = self.infer_type(first_return_value)
            else:
                return_type = "void" 
        
        # Ensure main returns int
        if node.name == 'main':
            return_type = 'int'
        
        # Convert function body
        body = []
        for stmt in node.body:
            body.append(self.visit(stmt))
        
        # Add return 0 to main if not present
        if node.name == 'main' and not any(isinstance(n, ast.Return) for n in ast.walk(ast.Module(body=node.body))):
            body.append("return 0;")
        
        # Restore original declared_vars after function scope
        self.declared_vars = original_declared_vars

        # Ensure correct newlines within the function body
        return f"{return_type} {node.name}({', '.join(params)}) {{\n{self.indent('\n'.join(body))}\n}}"

    def get_type(self, node):
        """Infer C type from Python node."""
        if isinstance(node, ast.Constant):
            if isinstance(node.value, str):
                return "char*"
            elif isinstance(node.value, (int, float)):
                return "int"
            elif isinstance(node.value, bool):
                return "int"
        elif isinstance(node, ast.List):
            if node.elts:
                element_type = self.get_type(node.elts[0])
                return f"{element_type}*"
            return "int*"
        elif isinstance(node, ast.Name):
            if node.id in self.declared_vars:
                return self.declared_vars[node.id]
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id == "str":
                    return "char*"
                elif node.func.id in ["int", "float"]:
                    return "int"
        return "int"  # Default type

    def visit_Assign(self, node):
        """Convert Python assignment to C."""
        if len(node.targets) != 1:
            self.warnings.append("Multiple assignment targets not supported")
            return "// Multiple assignment targets not supported"
        
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            self.warnings.append("Complex assignment target not supported")
            return "// Complex assignment target not supported"
            
        value = node.value
        target_id = target.id
        
        # Handle string initialization or assignment
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            # Declare as char* and use strdup for literals
            if target_id not in self.declared_vars:
                self.declared_vars[target_id] = "char*"
                return f"char* {target_id} = strdup({self.visit(value)}); // String literal assignment"
            else:
                # Re-assignment of string. Needs free() for previous memory and new strdup.
                # For simplicity, if already char*, just reassign with strdup.
                # A proper solution would require memory management (free old, strdup new).
                if self.declared_vars[target_id] == "char*":
                    self.warnings.append(f"Re-assigning string variable '{target_id}'. Consider explicit memory management (free/realloc).")
                    return f"{target_id} = strdup({self.visit(value)}); // String re-assignment"
                else: # Type change, not supported directly
                    self.warnings.append(f"Attempted to assign string to non-string variable '{target_id}' of type '{self.declared_vars[target_id]}'.")
                    return f"// ERROR: Type mismatch for {target_id}"
        
        # Handle assignments from function calls
        if isinstance(value, ast.Call):
            if isinstance(value.func, ast.Name) and value.func.id == "len":
                # Assuming len() is called on a string or list/array
                if value.args:
                    arg_name = self.visit(value.args[0])
                    # If it's a string, use strlen. If it's an array, use its _size variable.
                    arg_type = self.infer_type(value.args[0])
                    if arg_type == "char*":
                        if target_id not in self.declared_vars:
                            self.declared_vars[target_id] = "int"
                            return f"int {target_id} = strlen({arg_name});"
                        else:
                            return f"{target_id} = strlen({arg_name});"
                    elif arg_type.endswith('*'): # For arrays like int*
                        if target_id not in self.declared_vars:
                            self.declared_vars[target_id] = "int"
                            return f"int {target_id} = {arg_name}_size;"
                        else:
                            return f"{target_id} = {arg_name}_size;"

        # Get the type of the value
        value_type = self.infer_type(value)
        
        # Handle array initialization (Python list to C array)
        if isinstance(value, ast.List):
            size = len(value.elts)
            elements = ", ".join(self.visit(elt) for elt in value.elts)
            
            # Infer the base type of the array elements
            if value.elts:
                elem_type = self.infer_type(value.elts[0])
            else:
                elem_type = 'int' # Default for empty list

            self.declared_vars[target_id] = f'{elem_type}*'
            self.declared_vars[f'{target_id}_size'] = 'int'
            
            return f"{elem_type} {target_id}[{size}] = {{{elements}}};\nint {target_id}_size = {size};"
            
        # If variable not declared, declare it with its inferred type
        if target_id not in self.declared_vars:
            self.declared_vars[target_id] = value_type
            return f"{value_type} {target_id} = {self.visit(value)};"
        
        # If variable already declared, just assign
        return f"{target_id} = {self.visit(value)};"

    def visit_Call(self, node):
        """Convert Python function call to C."""
        if isinstance(node.func, ast.Name):
            if node.func.id == 'print':
                if not node.args:
                    return 'printf("\\n");'
                
                parts = []
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        parts.append(f'printf("{arg.value}")')
                    else:
                        if isinstance(arg, ast.Name) and arg.id in self.declared_vars:
                            var_type = self.declared_vars[arg.id]
                            if var_type == 'char*':
                                parts.append(f'printf("%s", {arg.id})')
                            elif var_type == 'float':
                                parts.append(f'printf("%.2f", {arg.id})')
                            else:
                                parts.append(f'printf("%d", {arg.id})')
                        else:
                            parts.append(f'printf("%d", {self.visit(arg)})')
                
                if not (isinstance(node.keywords, list) and any(k.arg == 'end' and k.value.value == '' for k in node.keywords)):
                    parts.append('printf("\\n")')
                
                return '; '.join(parts) + ';'
            elif node.func.id == 'len':
                if node.args and isinstance(node.args[0], ast.Name):
                    arg_name = node.args[0].id
                    if arg_name in self.declared_vars:
                        var_type = self.declared_vars[arg_name]
                        if var_type == 'char*':
                            return f"strlen({arg_name})"
                        elif var_type.endswith('*'):
                            return f"{arg_name}_size"
                self.warnings.append("len() call on non-array/string or undeclared variable. Falling back to default int value.")
                return "0" 
            
            # Handle array and string functions
            if len(node.args) > 0:
                first_arg = node.args[0]
                if isinstance(first_arg, ast.Name) and first_arg.id in self.declared_vars:
                    arg_type = self.declared_vars[first_arg.id]
                    if arg_type == 'char*':
                        if node.func.id == 'reverse_string':
                            return f"reverse_string({first_arg.id}, strlen({first_arg.id}))" 
                    elif arg_type.endswith('*'):
                        if node.func.id == 'sum_array':
                            return f"sum_array({first_arg.id}, {first_arg.id}_size)"
            
            # Handle general function calls
            func = self.visit(node.func)
            args = [self.visit(arg) for arg in node.args]
        return f"{func}({', '.join(args)})"

        self.warnings.append("Complex function call not supported")
        return "// Complex function call not supported"

    def visit_For(self, node):
        """Convert Python for loop to C."""
        if not isinstance(node.target, ast.Name):
            self.warnings.append("Complex for loop target not supported")
            return "// Complex for loop target not supported"
            
        target = node.target.id
        
        # Handle array/string iteration
        if isinstance(node.iter, ast.Name):
            iter_var = node.iter.id
            if iter_var in self.declared_vars:
                var_type = self.declared_vars[iter_var]
                if var_type == "char*":
                    # For string iteration, use strlen
                    loop_body_lines = [self.visit(stmt) for stmt in node.body]
                    # Introduce the character variable in the loop body
                    loop_body_lines.insert(0, f"char {target} = {iter_var}[{target}_idx];")
                    return f"for (int {target}_idx = 0; {target}_idx < strlen({iter_var}); {target}_idx++) {{\n{self.indent('\n'.join(loop_body_lines))}\n}}"
                elif var_type.endswith("*"): # For other array types
                    # For array iteration, use the size variable
                    loop_body_lines = [self.visit(stmt) for stmt in node.body]
                    # Introduce the element variable in the loop body
                    loop_body_lines.insert(0, f"{var_type[:-1]} {target} = {iter_var}[{target}_idx];")
                    return f"for (int {target}_idx = 0; {target}_idx < {iter_var}_size; {target}_idx++) {{\n{self.indent('\n'.join(loop_body_lines))}\n}}"
        
        # Handle range() calls
        if isinstance(node.iter, ast.Call) and isinstance(node.iter.func, ast.Name) and node.iter.func.id == "range":
            if len(node.iter.args) == 1:
                return f"for (int {target} = 0; {target} < {self.visit(node.iter.args[0])}; {target}++) {{\n{self.indent('\n'.join(self.visit(stmt) for stmt in node.body))}\n}}"
            elif len(node.iter.args) == 2:
                return f"for (int {target} = {self.visit(node.iter.args[0])}; {target} < {self.visit(node.iter.args[1])}; {target}++) {{\n{self.indent('\n'.join(self.visit(stmt) for stmt in node.body))}\n}}"
            
        self.warnings.append("Complex for loop not supported")
        return "// Complex for loop not supported"

    def visit_If(self, node: ast.If) -> str:
        """Convert a Python if statement to C."""
        self.indent_level += 1
        condition = self.visit(node.test)
        body = '\n'.join(self.visit(stmt) for stmt in node.body)
        else_body = ""
        if node.orelse:
            else_body = " else {\n" + self.indent('\n'.join(self.visit(stmt) for stmt in node.orelse)) + "\n}"
        self.indent_level -= 1
        return f"if ({condition}) {{\n{self.indent(body)}\n}}{else_body}"

    def visit_Compare(self, node: ast.Compare) -> str:
        """Convert a Python comparison to C."""
        if len(node.ops) != 1 or len(node.comparators) != 1:
            self.warnings.append("Multiple comparisons not supported")
            return "// Multiple comparisons not supported"
        
        left = self.visit(node.left)
        right = self.visit(node.comparators[0])
        op = self.visit(node.ops[0])
        
        # Handle string comparisons
        if isinstance(node.left, ast.Name) and node.left.id in self.declared_vars:
            var_type = self.declared_vars[node.left.id]
            if var_type == 'char*':
                if isinstance(node.ops[0], ast.Eq):
                    return f"strcmp({left}, {right}) == 0"
                elif isinstance(node.ops[0], ast.NotEq):
                    return f"strcmp({left}, {right}) != 0"
                elif isinstance(node.ops[0], ast.Lt):
                    return f"strcmp({left}, {right}) < 0"
                elif isinstance(node.ops[0], ast.LtE):
                    return f"strcmp({left}, {right}) <= 0"
                elif isinstance(node.ops[0], ast.Gt):
                    return f"strcmp({left}, {right}) > 0"
                elif isinstance(node.ops[0], ast.GtE):
                    return f"strcmp({left}, {right}) >= 0"
        
        # Handle arithmetic comparisons (default case)
        if isinstance(node.ops[0], ast.Eq):
            return f"{left} == {right}"
        elif isinstance(node.ops[0], ast.NotEq):
            return f"{left} != {right}"
        elif isinstance(node.ops[0], ast.Lt):
            return f"{left} < {right}"
        elif isinstance(node.ops[0], ast.LtE):
            return f"{left} <= {right}"
        elif isinstance(node.ops[0], ast.Gt):
            return f"{left} > {right}"
        elif isinstance(node.ops[0], ast.GtE):
            return f"{left} >= {right}"
        
        self.warnings.append("Unsupported comparison operator")
        return "// Unsupported comparison operator"

    def visit_BinOp(self, node):
        """Convert Python binary operation to C."""
        left = self.visit(node.left)
        op = self.visit(node.op)
        right = self.visit(node.right)

        # Special handling for string concatenation (Python uses +, C uses strcat)
        left_type = self.infer_type(node.left)
        right_type = self.infer_type(node.right)

        if isinstance(node.op, ast.Add) and ('char*' in [left_type, right_type] or 'char' in [left_type, right_type]):
            # If either operand is a string or a character, treat as string concatenation
            
            # Ensure operands are treated as C strings for strcat
            if isinstance(node.left, ast.Subscript) and left_type == 'char':
                left_str = f"(char[]){{ {left}, '\\0' }}"
            elif left_type == 'char*':
                left_str = left
            else:
                self.warnings.append(f"Attempting to concatenate non-string '{left_type}' to a string. Converting to strdup({left}).")
                left_str = f"strdup({left})" # Convert non-string to string (requires helper if not literal)

            if isinstance(node.right, ast.Subscript) and right_type == 'char':
                right_str = f"(char[]){{ {right}, '\\0' }}"
            elif right_type == 'char*':
                right_str = right
            else:
                self.warnings.append(f"Attempting to concatenate non-string '{right_type}' to a string. Converting to strdup({right}).")
                right_str = f"strdup({right})" # Convert non-string to string (requires helper if not literal)

            # Use strcat. Requires a temporary buffer or re-allocation.
            # For simplicity, we'll create a new string using dynamic allocation.
            self.warnings.append("String concatenation in C (using +) requires dynamic memory allocation and strcat. Manual memory management needed.")
            return f"strcat(strdup({left_str}), {right_str})"

        # Default binary operation for other types
        return f"({left} {op} {right})"

    def visit_Add(self, node):
        """Convert Python + to C."""
        return "+"

    def visit_Sub(self, node):
        """Convert Python - to C."""
        return "-"

    def visit_Mult(self, node):
        """Convert Python * to C."""
        return "*"

    def visit_Div(self, node):
        """Convert Python / to C."""
        return "/"
        
    def visit_Mod(self, node):
        """Convert Python % to C."""
        return "%"
        
    def visit_Compare(self, node):
        """Convert Python comparison to C."""
        left = self.visit(node.left)
        ops = [self.visit(op) for op in node.ops]
        comparators = [self.visit(comp) for comp in node.comparators]
        return f"({left} {ops[0]} {comparators[0]})"
        
    def visit_Eq(self, node):
        """Convert Python == to C."""
        return "=="
        
    def visit_NotEq(self, node):
        """Convert Python != to C."""
        return "!="
        
    def visit_Lt(self, node):
        """Convert Python < to C."""
        return "<"
        
    def visit_LtE(self, node):
        """Convert Python <= to C."""
        return "<="
        
    def visit_Gt(self, node):
        """Convert Python > to C."""
        return ">"
        
    def visit_GtE(self, node):
        """Convert Python >= to C."""
        return ">="
        
    def visit_BoolOp(self, node):
        """Convert Python boolean operation to C."""
        op = self.visit(node.op)
        values = [self.visit(v) for v in node.values]
        return f"({op.join(values)})"
        
    def visit_And(self, node):
        """Convert Python and to C."""
        return "&&"
        
    def visit_Or(self, node):
        """Convert Python or to C."""
        return "||"
        
    def visit_UnaryOp(self, node):
        """Convert Python unary operation to C."""
        op = self.visit(node.op)
        operand = self.visit(node.operand)
        return f"({op}{operand})"
        
    def visit_UAdd(self, node):
        """Convert Python + to C."""
        return "+"
        
    def visit_USub(self, node):
        """Convert Python - to C."""
        return "-"
        
    def visit_Not(self, node):
        """Convert Python not to C."""
        return "!"

    def visit_Return(self, node: ast.Return) -> str:
        """Convert a Python return statement to C."""
        if node.value:
            return f"return {self.visit(node.value)};" # Use self.visit
        return "return;"

    def visit_Name(self, node: ast.Name) -> str:
        """Convert a Python name to C."""
        if node.id in self.declared_vars:
            var_type = self.declared_vars[node.id]
            if var_type == 'char*':
                return f"{node.id}"
            elif var_type == 'float':
                return f"(float){node.id}"
            elif var_type == 'int*':
                return f"{node.id}"
            else:
                return f"{node.id}"
        
        # Handle built-in functions (these are more for identifying calls, not variables)
        if node.id == 'len':
            return 'sizeof' # This should typically be handled by visit_Call
        elif node.id == 'range':
            return 'for'   # This should typically be handled by visit_For
        elif node.id == 'print':
            return 'printf'
        elif node.id == 'str':
            return '(char*)' # Explicit cast for str() conversion
        elif node.id == 'int':
            return '(int)'
        elif node.id == 'float':
            return '(float)'
        elif node.id == 'bool':
            return '(int)'
        elif node.id == 'True':
            return '1'
        elif node.id == 'False':
            return '0'
        elif node.id == 'None':
            return 'NULL'
        
        # Handle arithmetic functions
        if node.id in ['add', 'subtract', 'multiply', 'divide']:
            return node.id
        
        # Handle string functions
        if node.id in ['reverse_string', 'strlen', 'strcat', 'strcpy', 'strdup']:
            return node.id
        
        # Handle array functions
        if node.id in ['sum_array']:
            return node.id
        
        self.warnings.append(f"Undefined variable: {node.id}")
        return node.id  # Return the variable name anyway to avoid syntax errors

    def visit_Subscript(self, node: ast.Subscript) -> str:
        """Convert a Python subscript to C."""
        value = self.visit(node.value)
        slice_expr = self.visit(node.slice)
        
        # Handle string indexing
        if isinstance(node.value, ast.Name) and node.value.id in self.declared_vars:
            var_type = self.declared_vars[node.value.id]
            if var_type == 'char*':
                return f"{value}[{slice_expr}]"
        
        # Handle array indexing
        if isinstance(node.value, ast.Name) and node.value.id in self.declared_vars:
            var_type = self.declared_vars[node.value.id]
            if var_type == 'int*':
                return f"{value}[{slice_expr}]"
        
        # Handle list indexing (if it infers to an array type)
        if isinstance(node.value, ast.List): # This path is less likely if list becomes int*
            return f"{value}[{slice_expr}]"
        
        # Handle string slicing (more complex, consider external helper function)
        if isinstance(node.slice, ast.Slice):
            if isinstance(node.value, ast.Name) and node.value.id in self.declared_vars:
                var_type = self.declared_vars[node.value.id]
                if var_type == 'char*':
                    # For string slicing, we need to create a new string
                    start = self.visit(node.slice.lower) if node.slice.lower else "0"
                    end = self.visit(node.slice.upper) if node.slice.upper else f"strlen({value})"
                    step = self.visit(node.slice.step) if node.slice.step else "1"
                    self.warnings.append("String slicing creates a new string with strndup. Requires memory management.")
                    return f"strndup({value} + {start}, {end} - {start})"
        
        # Handle array slicing (more complex, consider external helper function)
        if isinstance(node.slice, ast.Slice):
            if isinstance(node.value, ast.Name) and node.value.id in self.declared_vars:
                var_type = self.declared_vars[node.value.id]
                if var_type == 'int*':
                    # For array slicing, we need to create a new array copy
                    start = self.visit(node.slice.lower) if node.slice.lower else "0"
                    end = self.visit(node.slice.upper) if node.slice.upper else f"{value}_size"
                    step = self.visit(node.slice.step) if node.slice.step else "1"
                    self.warnings.append("Array slicing creates a new array copy. Requires memory management.")
                    return f"array_slice({value}, {start}, {end}, {step})"
        
        return f"{value}[{slice_expr}]"

    def visit_Index(self, node: ast.Index) -> str:
        """Convert a Python index to C."""
        return self.visit(node.value)

    def visit_Slice(self, node: ast.Slice) -> str:
        """Convert a Python slice to C."""
        lower = self.visit(node.lower) if node.lower else "0"
        upper = self.visit(node.upper) if node.upper else "0" # Upper is typically length for C, or 0 if not provided
        step = self.visit(node.step) if node.step else "1"
        self.warnings.append("Slice object conversion to C is often complex and may require custom helper functions beyond simple 'start:end:step' syntax.")
        return f"({lower}, {upper}, {step})" # Return as tuple for custom helper parsing

    def visit_List(self, node: ast.List) -> str:
        """Convert a Python list to a C array initializer."""
        elements = [self.visit(el) for el in node.elts]
        # Attempt to determine a common type for the elements
        if not elements:
            # For an empty list, we return an empty initializer for now. Type is handled by visit_Assign.
            return "{ /* empty */ }"
        
        # infer_type on the first element to get the base type for the array
        first_elem_type = self.infer_type(node.elts[0])

        # The type of the array itself is handled by visit_Assign, here we just produce the initializer.
        return f"{{ {', '.join(elements)} }}"

    def visit_Dict(self, node: ast.Dict) -> str:
        """Convert a Python dictionary to C struct."""
        if not node.keys:
            return "{}"
        pairs = []
        for key, value in zip(node.keys, node.values):
            key_str = self.visit(key)
            value_str = self.visit(value)
            # Assuming C struct member initialization like .key = value
            pairs.append(f".{key_str} = {value_str}")
        self.warnings.append("Python dictionaries are converted to C structs (if defined) or simple initializers. Complex dictionary operations may not be fully supported.")
        return f"{{ {', '.join(pairs)} }}" # Removed extra space after {{ to match C struct init style

    def visit_JoinedStr(self, node: ast.JoinedStr) -> str:
        """Convert a Python f-string to C."""
        parts = []
        format_str_parts = []
        args = []
        for value in node.values:
            if isinstance(value, ast.Constant):
                format_str_parts.append(value.value.replace('%', '%%')) # Escape % for printf
            elif isinstance(value, ast.FormattedValue):
                expr = self.visit(value.value)
                # Infer type for formatting specifier
                expr_type = self.infer_type(value.value)
                if expr_type == 'int':
                    format_str_parts.append("%d")
                elif expr_type == 'float':
                    format_str_parts.append("%.2f") # Default float precision
                elif expr_type == 'char*':
                    format_str_parts.append("%s")
                elif expr_type == 'char': # Single character from string indexing
                    format_str_parts.append("%c")
                else:
                    format_str_parts.append("%s") # Fallback to string
                args.append(expr)
        
        # For simplicity, convert f-string to a single printf if possible, or manual concatenation
        # This is a simplification and may not cover all f-string complexities
        if not args:
            return f"strdup(\"{''.join(format_str_parts)}\")"
        else:
            # For complex f-strings, a custom snprintf or string building might be needed.
            # Using snprintf requires knowing buffer size, which is hard to predict.
            # Returning a format string and args, assumes it's for printf/sprintf usage context.
            # Here, we'll build a string using sprintf for now.
            self.warnings.append("Complex f-strings may require a custom string building function in C (e.g., using snprintf to a buffer).")
            # This is a placeholder for actual f-string conversion to dynamic char*
            # A full implementation would involve calculating required buffer size and using snprintf
            # For now, let's return a warning and simplified concatenation.
            # This will require an external C helper for 'format_string' for robust handling.
            return f"format_string(\"{''.join(format_str_parts)}\", {', '.join(args)})"

    def visit_FormattedValue(self, node: ast.FormattedValue) -> str:
        """Convert a Python formatted value to C."""
        return self.visit(node.value)

    def visit_AugAssign(self, node: ast.AugAssign) -> str:
        """Convert a Python augmented assignment to C."""
        target = self.visit(node.target)
        value = self.visit(node.value)
        op = self.visit(node.op)
        return f"{target} {op}= {value};"

    def visit_Pow(self, node: ast.Pow) -> str:
        """Convert a Python power to C."""
        self.warnings.append("Python's ** (power) operator is converted to pow() function, which operates on floats. Implicit type casting may occur.")
        return "pow"

    def visit_LShift(self, node: ast.LShift) -> str:
        """Convert a Python left shift to C."""
        return "<<"

    def visit_RShift(self, node: ast.RShift) -> str:
        """Convert a Python right shift to C."""
        return ">>"

    def visit_BitOr(self, node: ast.BitOr) -> str:
        """Convert a Python bitwise OR to C."""
        return "|"

    def visit_BitXor(self, node: ast.BitXor) -> str:
        """Convert a Python bitwise XOR to C."""
        return "^"

    def visit_BitAnd(self, node: ast.BitAnd) -> str:
        """Convert a Python bitwise AND to C."""
        return "&"

    def visit_FloorDiv(self, node: ast.FloorDiv) -> str:
        """Convert a Python floor division to C."""
        return "/" # C integer division is floor division

    def visit_Is(self, node: ast.Is) -> str:
        """Convert 'is' to C equality."""
        self.warnings.append("Python 'is' operator (identity) is converted to C '==' (value equality). This may not be semantically identical for all types (e.g., object identity).")
        return "=="

    def visit_IsNot(self, node: ast.IsNot) -> str:
        """Convert 'is not' to C inequality."""
        self.warnings.append("Python 'is not' operator (identity) is converted to C '!=' (value inequality). This may not be semantically identical for all types (e.g., object identity).")
        return "!="

    def visit_In(self, node: ast.In) -> str:
        """Convert 'in' to a C 'contains' check (requires helper function)."""
        self.warnings.append("Python 'in' operator is converted to a 'contains' helper function (e.g., for arrays/strings). Requires custom C implementation.")
        return "contains" # Placeholder, requires custom C helper

    def visit_NotIn(self, node: ast.NotIn) -> str:
        """Convert 'not in' to a C '!contains' check (requires helper function)."""
        self.warnings.append("Python 'not in' operator is converted to a '!contains' helper function (e.g., for arrays/strings). Requires custom C implementation.")
        return "!contains" # Placeholder, requires custom C helper

    def visit_ListComp(self, node: ast.ListComp) -> str:
        """Convert a Python list comprehension to C."""
        self.warnings.append("Python list comprehensions are converted to explicit loops with an array/vector. Requires custom C helper functions for general cases.")
        # This is a simplified conversion; a full one requires more complex loop generation
        # and potentially dynamic array resizing or pre-allocation.
        target_expr = self.visit(node.elt)
        # Assuming a single generator for simplicity
        generator_iter = self.visit(node.generators[0].iter)
        generator_target = self.visit(node.generators[0].target)
        
        # A more robust conversion would involve creating a new array and looping
        # For now, return a placeholder that hints at the structure.
        return f"// List comprehension: create array, loop through {generator_iter}, add {target_expr} as {generator_target}"

    def visit_Attribute(self, node: ast.Attribute) -> str:
        """Convert a Python attribute access to C."""
        value = self.visit(node.value)
        
        # Handle string methods
        if isinstance(node.value, ast.Name) and node.value.id in self.declared_vars:
            var_type = self.declared_vars[node.value.id]
            if var_type == 'char*':
                # Map common Python string methods to C string functions
                if node.attr == 'lower':
                    self.warnings.append("Python str.lower() requires custom C implementation (e.g., converting each char to lower case).")
                    return f"strlwr({value})"
                elif node.attr == 'upper':
                    self.warnings.append("Python str.upper() requires custom C implementation (e.g., converting each char to upper case).")
                    return f"strupr({value})"
                elif node.attr == 'strip':
                    self.warnings.append("Python str.strip() requires custom C implementation (e.g., removing leading/trailing whitespace).")
                    return f"strtrim({value})"
                elif node.attr == 'replace':
                    self.warnings.append("Python str.replace() requires custom C implementation.")
                    return f"strreplace({value})"
                elif node.attr == 'split':
                    self.warnings.append("Python str.split() requires custom C implementation, returning array of strings.")
                    return f"strsplit({value})"
                elif node.attr == 'join':
                    self.warnings.append("Python str.join() requires custom C implementation.")
                    return f"strjoin({value})"
                elif node.attr == 'startswith':
                    self.warnings.append("Python str.startswith() requires custom C implementation (e.g., using strncmp).")
                    return f"strstartswith({value})"
                elif node.attr == 'endswith':
                    self.warnings.append("Python str.endswith() requires custom C implementation.")
                    return f"strendswith({value})"
                elif node.attr == 'find':
                    self.warnings.append("Python str.find() requires custom C implementation (e.g., using strstr and calculating offset).")
                    return f"strstr({value})" # strstr returns pointer, need to convert to index
                elif node.attr == 'count':
                    self.warnings.append("Python str.count() requires custom C implementation.")
                    return f"strcount({value})"
                elif node.attr == 'isdigit':
                    self.warnings.append("Python str.isdigit() requires custom C implementation.")
                    return f"isdigit_str({value})" # assuming helper for whole string
                elif node.attr == 'isalpha':
                    self.warnings.append("Python str.isalpha() requires custom C implementation.")
                    return f"isalpha_str({value})"
                elif node.attr == 'isalnum':
                    self.warnings.append("Python str.isalnum() requires custom C implementation.")
                    return f"isalnum_str({value})"
                elif node.attr == 'isspace':
                    self.warnings.append("Python str.isspace() requires custom C implementation.")
                    return f"isspace_str({value})"
                # ... add more string methods as needed, with warnings for custom C implementation

        # Handle array methods (similar to Python list methods)
        if isinstance(node.value, ast.Name) and node.value.id in self.declared_vars:
            var_type = self.declared_vars[node.value.id]
            if var_type == 'int*': # Assuming int array
                if node.attr == 'append':
                    self.warnings.append("Python list.append() requires custom C implementation (e.g., dynamic array resizing).\n")
                    return f"array_append({value})"
                elif node.attr == 'extend':
                    self.warnings.append("Python list.extend() requires custom C implementation.\n")
                    return f"array_extend({value})"
                elif node.attr == 'insert':
                    self.warnings.append("Python list.insert() requires custom C implementation.\n")
                    return f"array_insert({value})"
                elif node.attr == 'remove':
                    self.warnings.append("Python list.remove() requires custom C implementation.\n")
                    return f"array_remove({value})"
                elif node.attr == 'pop':
                    self.warnings.append("Python list.pop() requires custom C implementation.\n")
                    return f"array_pop({value})"
        
        self.warnings.append(f"Unsupported attribute access: {value}.{node.attr}")
        return f"{value}.{node.attr}" # Fallback for other attributes

    def infer_type(self, value):
        """Infer C type from Python value."""
        if isinstance(value, (ast.Assign, ast.AugAssign, ast.For, ast.If, ast.While)):
            self.warnings.append(f"Warning: infer_type received a statement node ({type(value).__name__}). Returning default type.")
            return 'int' # This should ideally not happen if calls are structured correctly

        if isinstance(value, ast.Constant):
            if isinstance(value.value, int):
                return 'int'
            elif isinstance(value.value, float):
                return 'float' # Use float for C
            elif isinstance(value.value, str):
                return 'char*' # Use char* for C strings
            elif isinstance(value.value, bool):
                return 'int' # Use int (0 or 1) for C bool
            elif value.value is None:
                return 'void*' # Use void* for None
        elif isinstance(value, ast.List):
            if value.elts:
                # Infer element type, assume uniform list type
                elem_type = self.infer_type(value.elts[0])
                return f'{elem_type}*' # Array type (pointer to element type)
            return 'int*' # Default to int array for empty list
        elif isinstance(value, ast.Name):
            if value.id in self.declared_vars:
                return self.declared_vars[value.id]
            elif value.id in self.struct_members:
                return self.struct_members[value.id]
            return 'int' # Default, hoping assignment or a later pass refines it.
        elif isinstance(value, ast.BinOp):
            left_type = self.infer_type(value.left)
            right_type = self.infer_type(value.right)
            if 'char*' in [left_type, right_type]:
                return 'char*'
            elif 'float' in [left_type, right_type]:
                return 'float'
            return 'int'
        elif isinstance(value, ast.Subscript):
            if isinstance(value.value, ast.Name) and value.value.id in self.declared_vars:
                array_type = self.declared_vars[value.value.id]
                if array_type.endswith('*'):
                    return array_type[:-1] # Return the base type (e.g., 'int*' -> 'int')
            return 'int' # Default if array type cannot be determined or not an array
        elif isinstance(value, ast.Call):
            if isinstance(value.func, ast.Name):
                # Explicitly define return types for known functions
                if value.func.id in ['str', 'strdup', 'strcat', 'reverse_string']:
                    return 'char*'
                elif value.func.id in ['sum_array', 'len', 'int']:
                    return 'int'
                elif value.func.id == 'float':
                    return 'float'
            return 'int' # Default return type for unknown functions
        elif isinstance(value, ast.UnaryOp):
            return self.infer_type(value.operand)
        return 'int' # Default for unhandled value types

    def infer_return_type(self, node):
        """Infer the return type of a function based on its body."""
        for stmt in node.body:
            if isinstance(stmt, ast.Return):
                if stmt.value:
                    return self.infer_type(stmt.value)
        return 'void' # Default to void if no return statement found

    def visit_ClassDef(self, node: ast.ClassDef) -> str:
        """Convert a Python class to C struct with function pointers."""
        self.indent_level += 1
        self.struct_members = {}
        
        # First pass: collect member variables
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        self.struct_members[target.id] = self.infer_type(item.value)
        
        # Second pass: generate struct definition
        body = []
        
        # Add member variables
        for name, type_ in self.struct_members.items():
            body.append(f"    {type_} {name};")
        
        # Add function pointers (methods)
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                if item.name == '__init__':
                    continue  # Skip __init__ as we handle it in constructor
                return_type = self.infer_return_type(item)
                # Arguments for function pointer declaration
                args = [f"{self.infer_type(arg) or 'int'} {arg.arg}" for arg in item.args.args]
                body.append(f"    {return_type} (*{item.name})({', '.join(args)});")
        
        self.indent_level -= 1
        self.warnings.append(f"Python classes are converted to C structs. Methods are represented as function pointers within the struct, requiring manual instantiation/binding logic in C.")
        return f"typedef struct {{\n{self.indent('\n'.join(body))}\n}} {node.name};"
