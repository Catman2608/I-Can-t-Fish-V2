def remove_blank_lines(input_file, output_file):
    # Read with error handling - replaces problematic characters with '?'
    with open(input_file, 'r', encoding='utf-8', errors='replace') as infile:
        lines = infile.readlines()
    
    non_blank_lines = []
    for line in lines:
        stripped = line.strip()
        # Check if line is empty OR contains only spaces and a # (empty comment)
        if stripped == '' or stripped == '#':
            if input_py.endswith("py"):
                skip_condition = last_stripped.startswith("return") or last_stripped.startswith("continue") or last_stripped.startswith("break") or last_stripped.startswith("pass") or last_stripped.startswith("raise")
            else:
                skip_condition = last_stripped.endswith("}")
            if skip_condition == False:
                continue  # Skip this line
        last_stripped = stripped
        non_blank_lines.append(line)
    
    with open(output_file, 'w', encoding='utf-8') as outfile:
        outfile.writelines(non_blank_lines)

# Usage
input_py = input("Input file: ")
output_py = input("Output file: ")

remove_blank_lines(input_py, output_py)
print(f"Blank lines removed from {input_py} and saved to {output_py}.")