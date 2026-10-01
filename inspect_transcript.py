import json
import sys

with open(r'C:\Users\ragib\.gemini\antigravity-ide\brain\58ebce1a-55de-44af-b6d6-5878f973ad7b\.system_generated\logs\transcript_full.jsonl', encoding='utf-8') as f:
    for line in f:
        obj = json.loads(line)
        if obj.get('step_index') in [63, 64, 71, 72, 73, 74, 75]:
            print(f"=== STEP {obj.get('step_index')} ({obj.get('type')}) ===")
            content = str(obj.get('content', ''))
            print(content[:1500].encode('ascii', errors='replace').decode('ascii'))
            tools = obj.get('tool_calls', [])
            if tools:
                print("TOOLS:", json.dumps(tools)[:500])
            print("\n" + "="*50 + "\n")
