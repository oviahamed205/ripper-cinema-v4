import re
import subprocess

with open('playmate_core.js', 'r', encoding='utf-8') as f:
    text = f.read()

# Let's find _0x1167 precisely
start_1167 = text.find('function _0x1167()')
end_1167 = text.find('return _0x1167();}', start_1167) + len('return _0x1167();}')
f_1167 = text[start_1167:end_1167]

start_4d3c = text.find('function _0x4d3c(')
end_4d3c = text.find('return!_0x592b0e?(_0x4537c7=_0x4d3c[\'DhcROA\'](_0x4537c7),_0x4d3c[\'cKishZ\'][_0x1322dc]=_0x4537c7):_0x4537c7=_0x592b0e,_0x4537c7;}', start_4d3c) + len('return!_0x592b0e?(_0x4537c7=_0x4d3c[\'DhcROA\'](_0x4537c7),_0x4d3c[\'cKishZ\'][_0x1322dc]=_0x4537c7):_0x4537c7=_0x592b0e,_0x4537c7;}')
f_4d3c = text[start_4d3c:end_4d3c]

m_iife = re.search(r'\(function\(_0x2782b3,_0x434fc2\)\{.*?\}\(_0x1167,.*?\)\);', text).group(0)

runner_js = f"""
{f_1167}
{f_4d3c}
{m_iife}

var _0xdea39b = _0x4d3c;

console.log("apiURL _0xdea39b(0x4a3) =", _0xdea39b(0x4a3));
console.log("filecode param _0xdea39b(0x1ec) =", _0xdea39b(0x1ec));
console.log("sx (streaming_url) =", _0xdea39b(0x244) + 'g_url');
"""

with open("run_pm_decode_clean.js", "w", encoding="utf-8") as f:
    f.write(runner_js)

res = subprocess.run(["node", "run_pm_decode_clean.js"], capture_output=True, text=True)
print("NODE OUTPUT:")
print(res.stdout)
print("NODE ERROR:")
print(res.stderr)
