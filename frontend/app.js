// Load Monaco Editor
require.config({ paths: { vs: 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.36.1/min/vs' } });

require(['vs/editor/editor.main'], function () {
    // Editor Initialization
    const pythonEditor = monaco.editor.create(document.getElementById('pythonEditor'), {
        value: '# Enter your Python code here\n',
        language: 'python',
        theme: 'vs',
        automaticLayout: true,
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
        fontSize: 14,
        tabSize: 4
    });

    const outputEditor = monaco.editor.create(document.getElementById('outputEditor'), {
        value: '',
        language: 'cpp',
        theme: 'vs',
        automaticLayout: true,
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
        fontSize: 14,
        tabSize: 4,
        readOnly: true
    });

    // Constants
    const API_BASE_URL = 'http://localhost:5000';
    let isDarkMode = false;
    let targetLanguage = 'c';

    // DOM Elements
    const themeToggle = document.getElementById('themeToggle');
    const convertToC = document.getElementById('convertToC');
    const convertToCpp = document.getElementById('convertToCpp');
    const convertBtn = document.getElementById('convertBtn');
    const clearBtn = document.getElementById('clearBtn');
    const copyBtn = document.getElementById('copyBtn');
    const downloadBtn = document.getElementById('downloadBtn');

    // Theme Toggle Logic
    themeToggle.addEventListener('click', () => {
        isDarkMode = !isDarkMode;
        document.documentElement.setAttribute('data-theme', isDarkMode ? 'dark' : 'light');
        monaco.editor.setTheme(isDarkMode ? 'vs-dark' : 'vs');
    });

    // Language Toggle
    convertToC.addEventListener('click', () => {
        targetLanguage = 'c';
        convertToC.classList.add('active');
        convertToCpp.classList.remove('active');
        outputEditor.updateOptions({ language: 'c' });
    });

    convertToCpp.addEventListener('click', () => {
        targetLanguage = 'cpp';
        convertToCpp.classList.add('active');
        convertToC.classList.remove('active');
        outputEditor.updateOptions({ language: 'cpp' });
    });

    // Transpile Code
    convertBtn.addEventListener('click', async () => {
        const pythonCode = pythonEditor.getValue();
        if (!pythonCode.trim()) {
            showWarning('Please enter some Python code to convert.');
            return;
        }

        try {
            const endpoint = targetLanguage === 'c' ? '/convert-to-c' : '/convert-to-cpp';
            const response = await fetch(`${API_BASE_URL}${endpoint}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ python_code: pythonCode })
            });

            const data = await response.json();

            if (response.ok) {
                outputEditor.setValue(data.converted_code);
                showWarnings(data.warnings);
            } else {
                showWarning(data.error || 'Conversion failed');
            }
        } catch (error) {
            console.error('Error:', error);
            showWarning('Error connecting to the server. Make sure the backend server is running on port 5000.');
        }
    });

    // Clear Code
    clearBtn.addEventListener('click', () => {
        pythonEditor.setValue('');
        outputEditor.setValue('');
        clearWarnings();
    });

    // Copy Output
    copyBtn.addEventListener('click', () => {
        const outputCode = outputEditor.getValue();
        if (outputCode) {
            navigator.clipboard.writeText(outputCode)
                .then(() => showWarning('Code copied to clipboard!', 'success'))
                .catch(() => showWarning('Failed to copy code'));
        }
    });

    // Download Output
    downloadBtn.addEventListener('click', () => {
        const outputCode = outputEditor.getValue();
        if (outputCode) {
            const extension = targetLanguage === 'c' ? 'c' : 'cpp';
            const blob = new Blob([outputCode], { type: 'text/plain' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `converted_code.${extension}`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }
    });

    // Warning Display Helpers
    function showWarning(message, type = 'warning') {
        const warningsDiv = document.getElementById('warnings');
        const warningElement = document.createElement('div');
        warningElement.className = `warning ${type}`;
        warningElement.textContent = message;
        warningsDiv.appendChild(warningElement);
    }

    function showWarnings(warnings) {
        clearWarnings();
        if (warnings && warnings.length > 0) {
            warnings.forEach(warning => showWarning(warning));
        }
    }

    function clearWarnings() {
        const warningsDiv = document.getElementById('warnings');
        warningsDiv.innerHTML = '';
    }

    // Re-layout editors on window resize
    window.addEventListener('resize', () => {
        pythonEditor.layout();
        outputEditor.layout();
    });
});
