const fs = require('fs');

let js = fs.readFileSync('playmate_core.js', 'utf8');

// Find the string array and the decoder function at the top of the file
// The obfuscator uses a standard javascript-obfuscator pattern:
// var _0xdea39b = _0x4d3c;
// function _0x38dc() { return [...] }
// (function(_0x2782b3, _0x434fc2){ ... })(_0x38dc, 0x...);
// function _0x4d3c(_0x..., _0x...) { ... }

// Let's run the header in node to get the decoder function _0x4d3c
const match = js.match(/function\s+(_0x[a-f0-9]+)\s*\(\)\s*\{\s*var\s+_0x[a-f0-9]+=\[.*?\];\s*return\s+_0x[a-f0-9]+;\s*\}/s);
if (match) {
    console.log("Found string array function!");
}

// Let's extract the array definition and the rotation loop
const headerMatch = js.match(/(var\s+_0x[a-f0-9]+=_0x[a-f0-9]+;.*?function\s+_0x4d3c\(.*?\n\})/s);
if (headerMatch) {
    console.log("Found header!");
}
