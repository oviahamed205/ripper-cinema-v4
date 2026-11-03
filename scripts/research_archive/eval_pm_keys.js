const fs = require('fs');

let js = fs.readFileSync('playmate_core.js', 'utf8');

// Find function _0x1167
const f1 = js.indexOf('function _0x1167()');
const f2 = js.indexOf('function _0x4d3c(');
const f2_end = js.indexOf('function setupSubtitlesOnly(');

const chunk1 = js.substring(0, js.indexOf('var __pmCfg='));
const chunk_funcs = js.substring(f1);

const full_decoder = chunk1 + '\n' + chunk_funcs;

const vm = require('vm');
const sandbox = {
    window: { location: { search: '', href: '' } },
    navigator: { userAgent: 'Mozilla/5.0' },
    document: { addEventListener: () => {}, head: { appendChild: () => {} }, createElement: () => ({ style: {}, classList: { add: () => {} } }) },
    jwplayer: () => ({ on: () => {}, setup: () => {} }),
    console: console,
    setTimeout: () => {},
    setInterval: () => {}
};
vm.createContext(sandbox);
vm.runInContext(full_decoder, sandbox);

console.log("apiURL _0xdea39b(0x4a3) =", sandbox._0xdea39b(0x4a3));
console.log("filecode param _0xdea39b(0x1ec) =", sandbox._0xdea39b(0x1ec));
console.log("sx (streaming_url) =", sandbox._0xdea39b(0x244) + 'g_url');
