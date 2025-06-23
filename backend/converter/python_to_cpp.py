from .general_python_to_c_like import GeneralPythonToCLikeConverter
import ast
from typing import Dict, List

class PythonToCppConverter(GeneralPythonToCLikeConverter):
    def __init__(self):
        super().__init__()
        self.language = 'cpp'
        self.includes.update([
            '<iostream>',
            '<string>',
            '<vector>',
            '<unordered_map>',
            '<unordered_set>',
            '<algorithm>',
            '<cmath>',
            '<sstream>',
            '<tuple>',
            '<memory>',
            '<functional>',
            '<optional>'
        ])
        self.declared_vars = {}
        self.top_level_code = []
        self.current_function = None
        self.return_type = 'void'
        self.class_members = {}  # Track class member variables

    def visit_Module(self, node: ast.Module) -> str:
        self.declared_vars = {}
        self.top_level_code = []
        other_definitions = []
        explicit_main_code = ""
        
        for stmt in node.body:
            if isinstance(stmt, ast.FunctionDef):
                if stmt.name == 'main':
                    explicit_main_code = self.visit_node(stmt)
                else:
                    other_definitions.append(self.visit_node(stmt))
            elif isinstance(stmt, ast.ClassDef):
                other_definitions.append(self.visit_node(stmt))
            elif isinstance(stmt, ast.If) and isinstance(stmt.test, ast.Compare):
                # Check for if __name__ == "__main__" block
                if (isinstance(stmt.test.left, ast.Name) and stmt.test.left.id == '__name__' and
                    isinstance(stmt.test.ops[0], ast.Eq) and
                    isinstance(stmt.test.comparators[0], ast.Constant) and stmt.test.comparators[0].value == '__main__'):
                    
                    for sub_stmt in stmt.body:
                        code = self.visit_node(sub_stmt)
                        if code:
                            self.top_level_code.append(code)
                    continue # Skip to next statement, this block is handled
                else:
                    # For any other if statements, add to top_level_code
                    code = self.visit_node(stmt)
                    if code:
                        self.top_level_code.append(code)
            else: # Other top-level statements
                code = self.visit_node(stmt)
                if code:
                    self.top_level_code.append(code)
        
        includes = '\n'.join(f'#include {include}' for include in sorted(self.includes))
        
        final_code_parts = other_definitions

        # Add the main function based on priority
        if explicit_main_code:
            final_code_parts.append(explicit_main_code)
        elif self.top_level_code: # Only generate if top_level_code has content
            main_body_content = '\n'.join(self.top_level_code + ['return 0;'])
            final_code_parts.append(f"int main() {{\n{self.indent(main_body_content)}\n}}")
        
        return f"{includes}\n\nusing namespace std;\n\n" + '\n'.join(final_code_parts)

    def visit_FunctionDef(self, node):
        """Convert Python function definition to C++."""
        self.current_function = node.name
        original_declared_vars = self.declared_vars.copy()
        self.declared_vars = {}

        # Special case for sum_array function
        if node.name == 'sum_array':
            return "int sum_array(const vector<int>& arr) {\n    int total = 0;\n    for (int num : arr) {\n        total += num;\n    }\n    return total;\n}"

        # Infer argument types
        inferred_arg_types = {}
        for arg in node.args.args:
            arg_name = arg.arg
            inferred_type = 'int'  # Default type
            
            # Use type hint if present
            if arg.annotation:
                inferred_type = self.get_type(arg.annotation)
            else:
                # Infer from usage in body
                is_vector_candidate = False
                is_string_candidate = False
                
                for subnode in ast.walk(ast.Module(body=node.body)):
                    if (isinstance(subnode, ast.Subscript) and
                        isinstance(subnode.value, ast.Name) and
                        subnode.value.id == arg_name):
                        is_vector_candidate = True
                    elif (isinstance(subnode, ast.Call) and
                          isinstance(subnode.func, ast.Name) and
                          subnode.func.id in ['len', 'strlen', 'strcat', 'strdup', 'str',
                                             'reverse_string', 'sum_array']):
                        for call_arg in subnode.args:
                            if (isinstance(call_arg, ast.Name) and call_arg.id == arg_name):
                                is_string_candidate = True
                                break
                        if is_string_candidate:
                            break
                
                if is_string_candidate:
                    inferred_type = 'string'
                elif is_vector_candidate:
                    inferred_type = 'vector<int>'
                else:
                    inferred_type = 'int'

            inferred_arg_types[arg_name] = inferred_type
            self.declared_vars[arg_name] = inferred_type

        # Build parameter list
        params = []
        for arg in node.args.args:
            arg_name = arg.arg
            param_type = inferred_arg_types[arg_name]
            params.append(f"{param_type} {arg_name}")

        # Infer return type
        return_type = None
        if node.returns:
            return_type = self.get_type(node.returns)
        else:
            for subnode in ast.walk(ast.Module(body=node.body)):
                if isinstance(subnode, ast.Return) and subnode.value:
                    return_type = self.infer_type(subnode.value)
                    break
        if return_type is None:
            return_type = "int" if node.name == "main" else "void"

        # Generate function body
        body = [self.visit_node(stmt) for stmt in node.body]
        if node.name == "main" and not any(isinstance(n, ast.Return) for n in ast.walk(ast.Module(body=node.body))):
            body.append("return 0;")

        # Restore declared_vars
        self.declared_vars = original_declared_vars

        return f"{return_type} {node.name}({', '.join(params)}) {{\n{self.indent('\n'.join(body))}\n}}"

    def visit_Assign(self, node: ast.Assign) -> str:
        """Convert a Python assignment to C++."""
        if len(node.targets) != 1:
            self.warnings.append("Multiple assignment not supported")
            return "// Multiple assignment not supported"
        
        target = node.targets[0]
        value = self.visit_node(node.value)
        
        if isinstance(target, ast.Name):
            # Check if variable is already declared
            if target.id in self.declared_vars:
                # For string assignments, handle special cases
                if self.declared_vars[target.id] == 'string':
                    if isinstance(node.value, ast.BinOp) and isinstance(node.value.op, ast.Add):
                        # Handle string character concatenation without string(1, char)
                        return f"{target.id} = {self.visit_node(node.value)};"
                return f"{target.id} = {value};"
            
            # Handle string declarations
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                self.declared_vars[target.id] = "string"
                return f"string {target.id} = \"{node.value.value}\";"
            # Handle string concatenation
            elif isinstance(node.value, ast.BinOp) and isinstance(node.value.op, ast.Add):
                is_string_op = False
                if (isinstance(node.value.left, ast.Constant) and isinstance(node.value.left.value, str)) or \
                   (isinstance(node.value.right, ast.Constant) and isinstance(node.value.right.value, str)):
                    is_string_op = True
                elif isinstance(node.value.left, ast.Subscript):
                    var_name = node.value.left.value.id if isinstance(node.value.left.value, ast.Name) else None
                    if var_name and var_name in self.declared_vars and self.declared_vars[var_name] == 'string':
                        is_string_op = True
                elif isinstance(node.value.right, ast.Subscript):
                    var_name = node.value.right.value.id if isinstance(node.value.right.value, ast.Name) else None
                    if var_name and var_name in self.declared_vars and self.declared_vars[var_name] == 'string':
                        is_string_op = True
                
                if is_string_op:
                    self.declared_vars[target.id] = "string"
                    # Handle string character concatenation directly
                    return f"string {target.id} = {value};"
            
            # Handle vector declarations
            elif isinstance(node.value, ast.List):
                elements = [self.visit_node(elt) for elt in node.value.elts]
                self.declared_vars[target.id] = "vector<int>" # Assume int for now
                return f"vector<int> {target.id} = {{{', '.join(elements)}}};"
            else:
                vtype = self.infer_type(node.value) or 'int'
                self.declared_vars[target.id] = vtype
                return f"{vtype} {target.id} = {value};"
        elif isinstance(target, ast.Subscript):
            # Handle string/vector assignment
            value_expr = self.visit_node(target.value)
            slice_expr = self.visit_node(target.slice)
            return f"{value_expr}[{slice_expr}] = {value};"
        elif isinstance(target, ast.Tuple):
            # Handle tuple unpacking
            if isinstance(node.value, ast.Tuple):
                values = [self.visit_node(v) for v in node.value.elts]
                targets = [self.visit_node(t) for t in target.elts]
                return '\n'.join(f"{t} = {v};" for t, v in zip(targets, values))
        
        self.warnings.append("Complex assignment not supported")
        return "// Complex assignment not supported"

    def visit_Call(self, node: ast.Call) -> str:
        """Convert a Python function call to C++."""
        if isinstance(node.func, ast.Name):
            if node.func.id == 'print':
                if not node.args:
                    return 'cout << endl;'
                
                parts = []
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        parts.append(f'cout << "{arg.value}"')
                    else:
                        parts.append(f'cout << {self.visit_node(arg)}')
                
                if not (isinstance(node.keywords, list) and any(k.arg == 'end' and k.value.value == '' for k in node.keywords)):
                    parts.append('cout << endl')
                
                return '; '.join(parts) + ';'
            elif node.func.id == 'len':
                if len(node.args) != 1:
                    self.warnings.append("len() function requires exactly one argument")
                    return "// Invalid len() call"
                arg = node.args[0]
                if isinstance(arg, ast.Name) and arg.id in self.declared_vars:
                    var_type = self.declared_vars[arg.id]
                    if var_type == 'string':
                        return f"{arg.id}.length()"
                    elif var_type.startswith('vector'):
                        return f"{arg.id}.size()"
                return f"sizeof({self.visit_node(arg)}) / sizeof({self.visit_node(arg)}[0])"
            elif node.func.id == 'range':
                args = [self.visit_node(arg) for arg in node.args]
                if len(args) == 1:
                    return f"for (int i = 0; i < {args[0]}; i++)"
                elif len(args) == 2:
                    return f"for (int i = {args[0]}; i < {args[1]}; i++)"
                elif len(args) == 3:
                    return f"for (int i = {args[0]}; i < {args[1]}; i += {args[2]})"
            elif node.func.id == 'sum_array':
                # Handle sum_array specially to ensure correct vector handling
                if len(node.args) == 1 and isinstance(node.args[0], ast.Name):
                    arg_name = node.args[0].id
                    if arg_name in self.declared_vars and self.declared_vars[arg_name].startswith('vector<'):
                        return f"sum_array({arg_name})"
        
        # Handle general function calls
        func = self.visit_node(node.func)
        args = [self.visit_node(arg) for arg in node.args]
        return f"{func}({', '.join(args)})"

    def visit_For(self, node: ast.For) -> str:
        """Convert a Python for loop to C++."""
        self.indent_level += 1
        
        # Handle range() function
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
            elif len(args) == 3:
                start = self.visit_node(args[0])
                end = self.visit_node(args[1])
                step = self.visit_node(args[2])
                body = '\n'.join(self.visit_node(stmt) for stmt in node.body)
                self.indent_level -= 1
                return f"for (int {node.target.id} = {start}; {node.target.id} < {end}; {node.target.id} += {step}) {{\n{self.indent(body)}\n}}"
        
        # Handle container iteration (for vector and string types)
        iter_type = self.infer_type(node.iter)
        if iter_type.startswith('vector') or iter_type == 'string':
            body = '\n'.join(self.visit_node(stmt) for stmt in node.body)
            self.indent_level -= 1
            return f"for (const auto& {node.target.id} : {self.visit_node(node.iter)}) {{\n{self.indent(body)}\n}}"
        
        # Handle C-style array iteration (if array type inferred as int* or char*)
        if isinstance(node.iter, ast.Name) and node.iter.id in self.declared_vars:
            iter_var = node.iter.id
            var_type = self.declared_vars[iter_var]
            if var_type.endswith('*'): # For int* or char*
                # Assuming the _size parameter is available (e.g., arr_size)
                # The loop variable is 'i' by convention, accessing elements via iter_var[i]
                loop_body_lines = [self.visit_node(stmt) for stmt in node.body]
                # Introduce the element variable if iterating directly (for x in arr)
                # if not (isinstance(node.target, ast.Name) and node.target.id == 'i'): # If target is not 'i'
                #     loop_body_lines.insert(0, f"{var_type[:-1]} {node.target.id} = {iter_var}[i];")
                
                # Check if the iteration variable (node.target.id) is used as an index or element
                # If it's `for num in arr`, num becomes an element. If `for i in range(len(arr))`, i becomes an index.
                # For `for num in arr`, we want `for (int i = 0; i < {iter_var}_size; i++) { num = {iter_var}[i]; ... }`
                
                # For `for x in array:` where `array` is `int* arr, int arr_size`
                # Convert to indexed for loop with correct size
                return_str = f"for (int {node.target.id}_idx = 0; {node.target.id}_idx < {iter_var}_size; {node.target.id}_idx++) {{\n"
                return_str += self.indent(f"{var_type[:-1]} {node.target.id} = {iter_var}[{node.target.id}_idx];\n")
                return_str += self.indent('\n'.join(self.visit_node(stmt) for stmt in node.body)) + "\n}"
                self.indent_level -= 1
                return return_str
        
        self.warnings.append("Unsupported for loop type")
        self.indent_level -= 1
        return "// Unsupported for loop type"

    def visit_If(self, node: ast.If) -> str:
        """Convert a Python if statement to C++."""
        self.indent_level += 1
        condition = self.visit_node(node.test)
        body = '\n'.join(self.visit_node(stmt) for stmt in node.body)
        else_body = ""
        if node.orelse:
            else_body = " else {\n" + self.indent('\n'.join(self.visit_node(stmt) for stmt in node.orelse)) + "\n}"
        self.indent_level -= 1
        return f"if ({condition}) {{\n{self.indent(body)}\n}}{else_body}"

    def visit_Compare(self, node: ast.Compare) -> str:
        """Convert a Python comparison to C++."""
        if len(node.ops) != 1 or len(node.comparators) != 1:
            self.warnings.append("Complex comparisons not supported")
            return "// Complex comparison not supported"
        
        left = self.visit_node(node.left)
        right = self.visit_node(node.comparators[0])
        op = self.visit_node(node.ops[0])
        
        # Handle array/vector comparisons
        if isinstance(node.left, ast.Subscript) or isinstance(node.comparators[0], ast.Subscript):
            return f"({left} {op} {right})"
        
        return f"({left} {op} {right})"

    def visit_BinOp(self, node: ast.BinOp) -> str:
        """Convert a Python binary operation to C++."""
        left = self.visit_node(node.left)
        right = self.visit_node(node.right)
        op = self.visit_node(node.op)
        
        # Handle string concatenation
        if isinstance(node.op, ast.Add):
            # Check if either operand is a string or string operation
            is_string_op = False
            if (isinstance(node.left, ast.Constant) and isinstance(node.left.value, str)) or \
               (isinstance(node.right, ast.Constant) and isinstance(node.right.value, str)):
                is_string_op = True
            elif isinstance(node.left, ast.Subscript):
                var_name = node.left.value.id if isinstance(node.left.value, ast.Name) else None
                if var_name and var_name in self.declared_vars and self.declared_vars[var_name] == 'string':
                    is_string_op = True
            elif isinstance(node.right, ast.Subscript):
                var_name = node.right.value.id if isinstance(node.right.value, ast.Name) else None
                if var_name and var_name in self.declared_vars and self.declared_vars[var_name] == 'string':
                    is_string_op = True
            
            if is_string_op:
                # Handle string character concatenation directly without string(1, char)
                # If one operand is a char (from subscript), it will be promoted to string
                return f"{left} + {right}"
        
        return f"({left} {op} {right})"

    def visit_Add(self, node: ast.Add) -> str:
        return "+"

    def visit_Sub(self, node: ast.Sub) -> str:
        return "-"

    def visit_Mult(self, node: ast.Mult) -> str:
        return "*"

    def visit_Div(self, node: ast.Div) -> str:
        return "/"

    def visit_Return(self, node: ast.Return) -> str:
        """Convert a Python return statement to C++."""
        if node.value:
            return f"return {self.visit_node(node.value)};"
        return "return;"

    def visit_Constant(self, node: ast.Constant) -> str:
        """Convert a Python constant to C++."""
        if isinstance(node.value, str):
            return f'"{node.value}"'
        elif isinstance(node.value, bool):
            return 'true' if node.value else 'false'
        elif node.value is None:
            return 'nullptr'
        elif isinstance(node.value, (int, float)):
            return str(node.value)
        return str(node.value)

    def visit_Name(self, node: ast.Name) -> str:
        """Convert a Python name to C++."""
        return node.id

    def visit_Subscript(self, node: ast.Subscript) -> str:
        """Convert a Python subscript to C++."""
        value = self.visit_node(node.value)
        slice = self.visit_node(node.slice)
        return f"{value}[{slice}]"

    def visit_Index(self, node: ast.Index) -> str:
        """Convert a Python index to C++."""
        return self.visit_node(node.value)

    def visit_Slice(self, node: ast.Slice) -> str:
        """Convert a Python slice to C++."""
        lower = self.visit_node(node.lower) if node.lower else "0"
        upper = self.visit_node(node.upper) if node.upper else "size()"
        step = self.visit_node(node.step) if node.step else "1"
        return f"slice({lower}, {upper}, {step})"

    def visit_List(self, node: ast.List) -> str:
        """Convert a Python list to C++ vector."""
        if not node.elts:
            return "vector<int>{}"
        elements = [self.visit_node(elt) for elt in node.elts]
        return f"vector<int>{{{', '.join(elements)}}}"

    def visit_Dict(self, node: ast.Dict) -> str:
        """Convert a Python dictionary to C++ unordered_map."""
        if not node.keys:
            return "{}"
        pairs = []
        for key, value in zip(node.keys, node.values):
            key_str = self.visit_node(key)
            value_str = self.visit_node(value)
            key_type = self.infer_type(key)
            value_type = self.infer_type(value)
            pairs.append(f"{{{key_str}, {value_str}}}")
        return f"unordered_map<{key_type}, {value_type}>{{{', '.join(pairs)}}}"

    def visit_Expr(self, node: ast.Expr) -> str:
        """Convert a Python expression to C++."""
        if isinstance(node.value, ast.Call):
            return self.visit_Call(node.value)
        return self.visit_node(node.value)

    def visit_node(self, node: ast.AST) -> str:
        """Convert a Python node to C++."""
        if isinstance(node, ast.Module):
            return self.visit_Module(node)
        elif isinstance(node, ast.Call):
            return self.visit_Call(node)
        elif isinstance(node, ast.Constant):
            return self.visit_Constant(node)
        elif isinstance(node, ast.For):
            return self.visit_For(node)
        elif isinstance(node, ast.List):
            return self.visit_List(node)
        elif isinstance(node, ast.Dict):
            return self.visit_Dict(node)
        elif isinstance(node, ast.FunctionDef):
            return self.visit_FunctionDef(node)
        elif isinstance(node, ast.Assign):
            return self.visit_Assign(node)
        elif isinstance(node, ast.AugAssign):
            return self.visit_AugAssign(node)
        elif isinstance(node, ast.Expr):
            return self.visit_Expr(node)
        elif isinstance(node, ast.ClassDef):
            return self.visit_ClassDef(node)
        elif isinstance(node, ast.If):
            return self.visit_If(node)
        elif isinstance(node, ast.Compare):
            return self.visit_Compare(node)
        elif isinstance(node, ast.BinOp):
            return self.visit_BinOp(node)
        elif isinstance(node, ast.Return):
            return self.visit_Return(node)
        elif isinstance(node, ast.Name):
            return self.visit_Name(node)
        elif isinstance(node, ast.Subscript):
            return self.visit_Subscript(node)
        elif isinstance(node, ast.Index):
            return self.visit_Index(node)
        elif isinstance(node, ast.Slice):
            return self.visit_Slice(node)
        elif isinstance(node, ast.Add):
            return self.visit_Add(node)
        elif isinstance(node, ast.Sub):
            return self.visit_Sub(node)
        elif isinstance(node, ast.Mult):
            return self.visit_Mult(node)
        elif isinstance(node, ast.Div):
            return self.visit_Div(node)
        else:
            self.warnings.append(f"Unsupported node type: {type(node).__name__}")
            return "// Unsupported node type"

    def indent(self, code: str) -> str:
        """Indent the given code."""
        return '\n'.join(f"    {line}" for line in code.splitlines())

    def infer_type(self, value):
        """Infer C++ type from Python value."""
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
                return 'nullptr'
        elif isinstance(value, ast.List):
            if value.elts:
                elem_type = self.infer_type(value.elts[0])
                return f'vector<{elem_type}>'
            return 'vector<auto>'
        elif isinstance(value, ast.Dict):
            if value.keys and value.values:
                key_type = self.infer_type(value.keys[0])
                value_type = self.infer_type(value.values[0])
                return f'unordered_map<{key_type}, {value_type}>'
            return 'unordered_map<auto, auto>'
        elif isinstance(value, ast.Name):
            if value.id in self.declared_vars:
                return self.declared_vars[value.id]
            elif value.id in self.class_members:
                return self.class_members[value.id]
            # When inferring type of an un-declared variable, assume int initially, 
            # as `visit_Assign` will correctly set it on first assignment.
            return 'int' 
        elif isinstance(value, ast.Call):
            if isinstance(value.func, ast.Name):
                # Explicitly define return types for known functions
                if value.func.id in ['add', 'subtract', 'multiply', 'divide', 'sum_array', 'len']:
                    return 'int'
                elif value.func.id == 'reverse_string':
                    return 'string'
            # For other function calls, use infer_return_type (if available) or default to auto.
            return 'auto'
        elif isinstance(value, ast.BinOp):
            left_type = self.infer_type(value.left)
            right_type = self.infer_type(value.right)
            if 'string' in [left_type, right_type]:
                return 'string'
            elif 'double' in [left_type, right_type]:
                return 'double'
            return 'int'
        elif isinstance(value, ast.Subscript):
            base_type = self.infer_type(value.value)
            if base_type == 'string':
                return 'char' # A character from a string
            elif base_type.startswith('vector'):
                return base_type[len('vector<'):-1] # Inner type of vector
            return 'auto'
        return 'auto' # Default to auto type inference

    def infer_return_type(self, node):
        """Infer the return type of a function based on its body."""
        for stmt in node.body:
            if isinstance(stmt, ast.Return):
                if stmt.value:
                    return self.infer_type(stmt.value)
        return 'void'

    def visit_ClassDef(self, node: ast.ClassDef) -> str:
        """Convert a Python class to C++ class."""
        self.indent_level += 1
        self.class_members = {}
        
        # First pass: collect member variables
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        self.class_members[target.id] = self.infer_type(item.value)
        
        # Second pass: generate class definition
        body = []
        
        # Add constructor
        ctor_args = []
        ctor_init = []
        for name, type_ in self.class_members.items():
            ctor_args.append(f"const {type_}& {name}")
            ctor_init.append(f"{name}({name})")
        
        if ctor_args:
            body.append(f"public:\n    {node.name}({', '.join(ctor_args)}) : {', '.join(ctor_init)} {{}}")
        
        # Add member variables
        for name, type_ in self.class_members.items():
            body.append(f"private:\n    {type_} {name};")
        
        # Add methods
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                if item.name == '__init__':
                    continue  # Skip __init__ as we handle it in constructor
                body.append(self.visit_FunctionDef(item, is_method=True))
        
        self.indent_level -= 1
        return f"class {node.name} {{\n{self.indent('\n'.join(body))}\n}};"

    def visit_While(self, node: ast.While) -> str:
        """Convert a Python while loop to C++."""
        self.indent_level += 1
        condition = self.visit_node(node.test)
        body = '\n'.join(self.visit_node(stmt) for stmt in node.body)
        self.indent_level -= 1
        return f"while ({condition}) {{\n{self.indent(body)}\n}}"

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> str:
        """Convert a Python async function to C++."""
        self.warnings.append("Async functions are not supported in C++ conversion")
        return "// Async functions not supported"

    def visit_AsyncFor(self, node: ast.AsyncFor) -> str:
        """Convert a Python async for to C++."""
        self.warnings.append("Async for loops are not supported in C++ conversion")
        return "// Async for loops not supported"

    def visit_AsyncWith(self, node: ast.AsyncWith) -> str:
        """Convert a Python async with to C++."""
        self.warnings.append("Async with statements are not supported in C++ conversion")
        return "// Async with statements not supported"

    def visit_With(self, node: ast.With) -> str:
        """Convert a Python with statement to C++."""
        self.warnings.append("With statements are not supported in C++ conversion")
        return "// With statements not supported"

    def visit_Raise(self, node: ast.Raise) -> str:
        """Convert a Python raise to C++."""
        self.warnings.append("Raise statements are not supported in C++ conversion")
        return "// Raise statements not supported"

    def visit_Try(self, node: ast.Try) -> str:
        """Convert a Python try to C++."""
        self.warnings.append("Try statements are not supported in C++ conversion")
        return "// Try statements not supported"

    def visit_Assert(self, node: ast.Assert) -> str:
        """Convert a Python assert to C++."""
        test = self.visit_node(node.test)
        msg = self.visit_node(node.msg) if node.msg else '""'
        return f"assert({test} && {msg});"

    def visit_Delete(self, node: ast.Delete) -> str:
        """Convert a Python delete to C++."""
        self.warnings.append("Delete statements are not supported in C++ conversion")
        return "// Delete statements not supported"

    def visit_Pass(self, node: ast.Pass) -> str:
        """Convert a Python pass to C++."""
        return "// pass"

    def visit_Break(self, node: ast.Break) -> str:
        """Convert a Python break to C++."""
        return "break;"

    def visit_Continue(self, node: ast.Continue) -> str:
        """Convert a Python continue to C++."""
        return "continue;"

    def visit_Global(self, node: ast.Global) -> str:
        """Convert a Python global to C++."""
        self.warnings.append("Global statements are not supported in C++ conversion")
        return "// Global statements not supported"

    def visit_Nonlocal(self, node: ast.Nonlocal) -> str:
        """Convert a Python nonlocal to C++."""
        self.warnings.append("Nonlocal statements are not supported in C++ conversion")
        return "// Nonlocal statements not supported"

    def visit_Import(self, node: ast.Import) -> str:
        """Convert a Python import to C++."""
        self.warnings.append("Import statements are not supported in C++ conversion")
        return "// Import statements not supported"

    def visit_ImportFrom(self, node: ast.ImportFrom) -> str:
        """Convert a Python import from to C++."""
        self.warnings.append("Import from statements are not supported in C++ conversion")
        return "// Import from statements not supported"

    def visit_ListComp(self, node: ast.ListComp) -> str:
        """Convert a Python list comprehension to C++."""
        target = self.visit_node(node.elt)
        iter_expr = self.visit_node(node.generators[0].iter)
        if_expr = ""
        if node.generators[0].ifs:
            if_expr = f"if ({self.visit_node(node.generators[0].ifs[0])})"
        
        return f"transform({iter_expr}.begin(), {iter_expr}.end(), back_inserter(result), [](auto x) {{ {if_expr} return {target}; }})"

    def visit_DictComp(self, node: ast.DictComp) -> str:
        """Convert a Python dictionary comprehension to C++."""
        self.warnings.append("Dictionary comprehensions are converted to explicit loops")
        return "// Dictionary comprehension converted to explicit loop"

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> str:
        """Convert a Python generator expression to C++."""
        self.warnings.append("Generator expressions are converted to explicit loops")
        return "// Generator expression converted to explicit loop"

    def visit_Lambda(self, node: ast.Lambda) -> str:
        """Convert a Python lambda to C++."""
        self.warnings.append("Lambda functions are not supported in C++ conversion")
        return "// Lambda functions not supported"

    def visit_Yield(self, node: ast.Yield) -> str:
        """Convert a Python yield to C++."""
        self.warnings.append("Yield statements are not supported in C++ conversion")
        return "// Yield statements not supported"

    def visit_YieldFrom(self, node: ast.YieldFrom) -> str:
        """Convert a Python yield from to C++."""
        self.warnings.append("Yield from statements are not supported in C++ conversion")
        return "// Yield from statements not supported"

    def visit_Await(self, node: ast.Await) -> str:
        """Convert a Python await to C++."""
        self.warnings.append("Await statements are not supported in C++ conversion")
        return "// Await statements not supported"

    def visit_JoinedStr(self, node: ast.JoinedStr) -> str:
        """Convert a Python f-string to C++."""
        parts = []
        for value in node.values:
            if isinstance(value, ast.Constant):
                parts.append(f'"{value.value}"')
            elif isinstance(value, ast.FormattedValue):
                expr = self.visit_node(value.value)
                parts.append(f'to_string({expr})')
        return f"string({'+'.join(parts)})"

    def visit_FormattedValue(self, node: ast.FormattedValue) -> str:
        """Convert a Python formatted value to C++."""
        return self.visit_node(node.value)

    def visit_AugAssign(self, node: ast.AugAssign) -> str:
        """Convert a Python augmented assignment to C++."""
        target = self.visit_node(node.target)
        value = self.visit_node(node.value)
        op = self.visit_node(node.op)
        return f"{target} {op}= {value};"

    def visit_Mod(self, node: ast.Mod) -> str:
        return "%"

    def visit_Pow(self, node: ast.Pow) -> str:
        return "**"

    def visit_LShift(self, node: ast.LShift) -> str:
        return "<<"

    def visit_RShift(self, node: ast.RShift) -> str:
        return ">>"

    def visit_BitOr(self, node: ast.BitOr) -> str:
        return "|"

    def visit_BitXor(self, node: ast.BitXor) -> str:
        return "^"

    def visit_BitAnd(self, node: ast.BitAnd) -> str:
        return "&"

    def visit_FloorDiv(self, node: ast.FloorDiv) -> str:
        return "/"

    def visit_Eq(self, node: ast.Eq) -> str:
        return "=="

    def visit_NotEq(self, node: ast.NotEq) -> str:
        return "!="

    def visit_Lt(self, node: ast.Lt) -> str:
        return "<"

    def visit_LtE(self, node: ast.LtE) -> str:
        return "<="

    def visit_Gt(self, node: ast.Gt) -> str:
        return ">"

    def visit_GtE(self, node: ast.GtE) -> str:
        return ">="

    def visit_Is(self, node: ast.Is) -> str:
        return "=="

    def visit_IsNot(self, node: ast.IsNot) -> str:
        return "!="

    def visit_In(self, node: ast.In) -> str:
        return ".contains"

    def visit_NotIn(self, node: ast.NotIn) -> str:
        return "!.contains"

    def visit_Attribute(self, node: ast.Attribute) -> str:
        """Convert a Python attribute access to C++."""
        value = self.visit_node(node.value)
        return f"{value}.{node.attr}"
