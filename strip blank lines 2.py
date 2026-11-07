def remove_blank_lines(input_file, output_file):
    # Read with error handling - replaces problematic characters with '?'
    with open(input_file, 'r', encoding='utf-8', errors='replace') as infile:
        lines = infile.readlines()

    # Append each line of the file
    edited_file = []
    edit = []
    collapse = False

    for line in lines:
        if "(" in line and ")" not in line:
            collapse = True
        if ")" in line and "(" not in line:
            collapse = False

        if collapse:
            if not edit:
                # First line of the group: keep its leading indentation,
                # strip only the trailing newline.
                edit.append(line.rstrip("\n"))
            else:
                # Continuation lines: strip both ends.
                edit.append(line.strip())
        else:
            if edit:
                edit.append(line.strip())          # the closing line
                edited_file.append(" ".join(edit) + "\n")
                edit = []
            else:
                edited_file.append(line)           # untouched line
    
    # Write the kept lines
    with open(output_file, 'w', encoding='utf-8') as outfile:
        for i, line in enumerate(edited_file):
            outfile.write(line)

# Usage
input_py = input("Input file: ")
output_py = input("Output file: ")

remove_blank_lines(input_py, output_py)
print(f"Processed {input_py} and saved to {output_py}.")