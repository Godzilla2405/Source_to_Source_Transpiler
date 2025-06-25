# Python to C/C++ Code Converter

A web-based tool that converts Python code to equivalent C and C++ code. The converter uses Python's AST module to parse and transform code, providing a clean and intuitive interface for code conversion.

## Features

- Convert Python code to C or C++ with a single click
- Support for basic Python constructs:
  - Variables and basic data types
  - Control structures (if/else, for/while loops)
  - Function definitions
  - Basic I/O operations
- Real-time syntax highlighting
- Dark/light mode support
- Copy to clipboard and download functionality
- Warning system for unsupported features

## Project Structure

```
.
├── backend/
│   ├── app.py                 # Flask application
│   └── converter/
│       ├── base_converter.py  # Base converter class
│       ├── python_to_c.py     # Python to C converter
│       └── python_to_cpp.py   # Python to C++ converter
├── frontend/
│   ├── index.html            # Main HTML file
│   ├── styles.css            # CSS styles
│   └── app.js               # Frontend JavaScript
└── requirements.txt         # Python dependencies
```

## Installation

1. Clone the repository:
```bash
git clone <Godzilla2405/Source_to_Source_Transpiler)>
cd python-to-cpp-converter
```

2. Create a virtual environment and activate it:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install the required dependencies:
```bash
pip install -r requirements.txt
```

## Running the Application

1. Start the backend server:
```bash
cd backend
python app.py
```

2. Serve the frontend:
   - You can use any static file server
   - For development, you can use Python's built-in server:
```bash
cd frontend
python -m http.server 8000
```

3. Open your browser and navigate to `http://localhost:8000`

## Usage

1. Enter your Python code in the left editor
2. Choose the target language (C or C++)
3. Click "Convert" to transform the code
4. Use the output panel to view, copy, or download the converted code
5. Check the warnings panel for any unsupported features

## Supported Python Features

- Basic data types (int, float, str, bool)
- Control structures (if/else, for, while)
- Function definitions
- Basic I/O operations
- Variable declarations and assignments
- Arithmetic operations
- Comparison operations
- Logical operations

## Limitations

- Complex Python features are not supported
- Some Python standard library functions may not have direct equivalents
- Type inference is basic and may require manual adjustment
- List comprehensions and generator expressions are not supported
- Classes and object-oriented features are not supported

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
