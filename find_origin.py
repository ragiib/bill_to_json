import json

for conv_id in ['93d74bb6-3a09-4c40-b384-37f47b0103fd', '888bc9d8-c4ee-4310-9b13-a3e30a41fce7', '1e6ed109-0943-4bcf-8169-5d59953246ca', '58ebce1a-55de-44af-b6d6-5878f973ad7b']:
    p = rf"C:\Users\ragib\.gemini\antigravity-ide\brain\{conv_id}\.system_generated\logs\transcript_full.jsonl"
    try:
        with open(p, encoding='utf-8') as f:
            for line in f:
                obj = json.loads(line)
                c = str(obj.get('content', ''))
                if '2490.50' in c and obj.get('type') in ['USER_INPUT', 'PLANNER_RESPONSE', 'RUN_COMMAND']:
                    step = obj.get('step_index')
                    t = obj.get('type')
                    print(f"Conv {conv_id[:8]} Step {step} ({t}):")
                    print(c[:300].encode('ascii', errors='replace').decode('ascii'))
                    print('-'*40)
    except Exception as e:
        print(f"Error {conv_id}: {e}")
