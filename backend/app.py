from flask import Flask, request, jsonify
from flask_cors import CORS
import ast
from converter.python_to_c import PythonToCConverter
from converter.python_to_cpp import PythonToCppConverter

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": ["http://localhost:8000", "http://127.0.0.1:8000"]}})

@app.route('/convert-to-c', methods=['POST'])
def convert_to_c():
    try:
        data = request.get_json()
        if not data or 'python_code' not in data:
            return jsonify({'error': 'No Python code provided'}), 400
        
        python_code = data['python_code']
        converter = PythonToCConverter()
        result = converter.convert(python_code)
        
        return jsonify({
            'converted_code': result['code'],
            'warnings': result['warnings']
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/convert-to-cpp', methods=['POST'])
def convert_to_cpp():
    try:
        data = request.get_json()
        if not data or 'python_code' not in data:
            return jsonify({'error': 'No Python code provided'}), 400
        
        python_code = data['python_code']
        converter = PythonToCppConverter()
        result = converter.convert(python_code)
        
        return jsonify({
            'converted_code': result['code'],
            'warnings': result['warnings']
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/supported-features', methods=['GET'])
def supported_features():
    return jsonify({
        'features': [
            'Basic data types (int, float, str, bool)',
            'Control structures (if/else, for, while)',
            'Function definitions',
            'Basic I/O operations',
            'Variable declarations and assignments',
            'Arithmetic operations',
            'Comparison operations',
            'Logical operations'
        ]
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0') 