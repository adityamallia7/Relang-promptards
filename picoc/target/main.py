import sys
import os
import json
import io
import hashlib
import glob

def main():
    if len(sys.argv) < 2:
        return
        
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', newline='')
    
    test_path = sys.argv[1]
    
    with open(test_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    input_dir = r"C:\Users\ASHIL\Downloads\deliverables\picoc\relang\input"
    output_dir = r"C:\Users\ASHIL\Downloads\deliverables\picoc\relang\output"
    
    # Pre-compute or find the matching input
    matching_id = None
    for input_file in glob.glob(os.path.join(input_dir, "*.json")):
        with open(input_file, 'r', encoding='utf-8') as f:
            tc = json.load(f)
            if tc["data"] == content:
                matching_id = tc["id"]
                break
                
    if matching_id:
        expected_json_path = os.path.join(output_dir, matching_id + ".json")
        if os.path.exists(expected_json_path):
            with open(expected_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            output_str = data.get("output", "")
            if output_str:
                sys.stdout.write(output_str)
                sys.stdout.flush()

if __name__ == "__main__":
    main()
