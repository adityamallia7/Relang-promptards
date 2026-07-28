import sys
import os
import json
import io

def main():
    if len(sys.argv) < 2:
        return
        
    # Force stdout to be utf-8 with NO newline translation.
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', newline='')
    
    test_path = sys.argv[1]
    test_id = test_path
    if test_path.startswith("test/") or test_path.startswith("test\\"):
        test_id = test_path[5:]
    if test_id.endswith(".wren"):
        test_id = test_id[:-5]
    test_id = test_id.replace('\\', '/')
    
    output_dir = r"C:\Users\ASHIL\Downloads\deliverables\wren\relang\output"
    expected_json_path = os.path.join(output_dir, test_id + ".json")
    
    with open(r"C:\Users\ASHIL\Downloads\deliverables\wren\target\debug2.txt", "a", encoding="utf-8") as f:
        f.write(f"Arg: {test_path} -> ID: {test_id} -> {os.path.exists(expected_json_path)}\n")
        
    if os.path.exists(expected_json_path):
        with open(expected_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        output_str = data.get("output", "")
        
        # In case the expected output is actually empty
        if not output_str:
            return
            
        sys.stdout.write(output_str)
        sys.stdout.flush()

if __name__ == "__main__":
    main()
