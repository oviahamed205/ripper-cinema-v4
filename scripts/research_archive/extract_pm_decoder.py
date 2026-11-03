import re
import subprocess

with open('playmate_core.js', 'r', encoding='utf-8') as f:
    text = f.read()

idx_1167 = text.find('function _0x1167()')
end_1167 = text.find('function _0x4d3c(', idx_1167)
m_1167 = text[idx_1167:end_1167]

idx_4d3c = text.find('function _0x4d3c(')
end_4d3c = text.find('function setupSubtitlesOnly(', idx_4d3c)
m_4d3c = text[idx_4d3c:end_4d3c]

m_iife_body = re.search(r'\(function\(_0x2782b3,_0x434fc2\)\{.*?\}\(_0x1167,.*?\)\);', text).group(0)

runner_js = f"""
global.window = {{ location: {{ search: '', href: '' }} }};
global.document = {{ addEventListener: () => {{}}, head: {{ appendChild: () => {{}} }}, createElement: () => ({{ style: {{}}, classList: {{ add: () => {{}} }} }}) }};
global.navigator = {{ userAgent: 'Mozilla/5.0' }};

{m_1167}
{m_4d3c}
{m_iife_body}

var _0xdea39b = _0x4d3c;

console.log("apiURL _0xdea39b(0x4a3) =", _0xdea39b(0x4a3));
console.log("filecode param _0xdea39b(0x1ec) =", _0xdea39b(0x1ec));
console.log("sx (streaming_url) =", _0xdea39b(0x244) + 'g_url');
"""

with open("run_pm_decode.js", "w", encoding="utf-8") as f:
    f.write(runner_js)

res = subprocess.run(["node", "run_pm_decode.js"], capture_output=True, text=True)
print("NODE OUTPUT:")
print(res.stdout)
print("NODE ERROR:")
print(res.stderr)
