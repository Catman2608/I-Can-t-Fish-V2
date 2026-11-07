def remove_blank_lines(input_file, output_file):
    # Read with error handling - replaces problematic characters with '?'
    with open(input_file, 'r', encoding='utf-8', errors='replace') as infile:
        lines = infile.readlines()
    
    # Collect only the non-blank lines (and skip lone "#" comment lines)
    non_blank_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped == '' or stripped == '#':
            continue
        non_blank_lines.append(line)
    
    # Write the kept lines with a blank line between each pair
    with open(output_file, 'w', encoding='utf-8') as outfile:
        for i, line in enumerate(non_blank_lines):
            if i > 0:
                outfile.write('\n')
            outfile.write(line)

# Usage
input_py = input("Input file: ")
output_py = input("Output file: ")

remove_blank_lines(input_py, output_py)
print(f"Processed {input_py} and saved to {output_py}.")