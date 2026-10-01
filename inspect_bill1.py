import json

with open('test_fixtures/bill_1.extracted.json', encoding='utf-8') as f:
    d = json.load(f)

for idx, it in enumerate(d['line_items']):
    desc = it["description"]["value"]
    qty = it["quantity"]["value"]
    rate = it["rate"]["value"]
    taxable = it["taxable_value"]["value"]
    amt = it["amount"]["value"]
    print(f"{idx+1}: {desc} | qty={qty} | rate={rate} | taxable={taxable} | amt={amt}")

print("Sum of taxable:", sum(it['taxable_value']['value'] for it in d['line_items'] if it['taxable_value']['value'] is not None))
print("Sum of amounts:", sum(it['amount']['value'] for it in d['line_items'] if it['amount']['value'] is not None))
