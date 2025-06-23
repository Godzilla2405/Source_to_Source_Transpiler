def add(a, b):
    return a + b

def subtract(a, b):
    return a - b

def multiply(a, b):
    return a * b

def divide(a, b):
    return a / b

def sum_array(arr):
    total = 0
    for i in range(len(arr)):
        total = total + arr[i]
    return total

def reverse_string(text):
    result = ""
    for i in range(len(text)):
        result = text[i] + result
    return result

def main():
    # Test arithmetic functions
    x = 10
    y = 5
    print("Addition:", add(x, y))
    print("Subtraction:", subtract(x, y))
    print("Multiplication:", multiply(x, y))
    print("Division:", divide(x, y))
    
    # Test array sum
    numbers = [1, 2, 3, 4, 5]
    result = sum_array(numbers)
    print("Array sum:", result)
    
    # Test string reversal
    message = "Hello"
    reversed_message = reverse_string(message)
    print("Original:", message)
    print("Reversed:", reversed_message)

if __name__ == "__main__":
    main()