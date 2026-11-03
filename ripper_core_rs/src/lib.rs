use pyo3::prelude::*;
use regex::Regex;
use xxhash_rust::xxh64::xxh64;

const ALPHABET_62: &[u8] = b"0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ";
const ALPHABET_95: &[u8] = br#" !"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\]^_`abcdefghijklmnopqrstuvwxyz{|}~"#;

fn unbase(token: &str, radix: u32) -> i64 {
    if (2..=36).contains(&radix) {
        return i64::from_str_radix(token, radix).unwrap_or(-1);
    }
    let alphabet = if radix > 62 { ALPHABET_95 } else { ALPHABET_62 };
    let mut ret: i64 = 0;
    for &b in token.as_bytes() {
        if let Some(pos) = alphabet.iter().position(|&x| x == b) {
            let pos = pos as u32;
            if pos >= radix {
                return -1;
            }
            ret = ret * (radix as i64) + (pos as i64);
        } else {
            return -1;
        }
    }
    ret
}

#[pyfunction]
fn fast_hash64(data: &str) -> PyResult<String> {
    let hash = xxh64(data.as_bytes(), 0);
    Ok(format!("{:016x}", hash))
}

#[pyfunction]
fn unpack_packer(source: &str) -> PyResult<String> {
    if !source.contains("eval(function(p,a,c,k,e,") {
        return Ok(source.to_string());
    }

    let re1 = Regex::new(r"\}\('(.*?)', *(\d+|\[\]), *(\d+), *'(.*?)'\.split\('\|'\), *(\d+), *(.*?)\)\)").unwrap();
    let re2 = Regex::new(r"\}\('(.*?)', *(\d+|\[\]), *(\d+), *'(.*?)'\.split\('\|'\)").unwrap();

    let (payload, radix, symtab) = if let Some(caps) = re1.captures(source) {
        let p = caps.get(1).map(|m| m.as_str()).unwrap_or("");
        let r_str = caps.get(2).map(|m| m.as_str()).unwrap_or("62");
        let r: u32 = if r_str == "[]" { 62 } else { r_str.parse().unwrap_or(62) };
        let s = caps.get(4).map(|m| m.as_str()).unwrap_or("");
        (p, r, s.split('|').collect::<Vec<&str>>())
    } else if let Some(caps) = re2.captures(source) {
        let p = caps.get(1).map(|m| m.as_str()).unwrap_or("");
        let r_str = caps.get(2).map(|m| m.as_str()).unwrap_or("62");
        let r: u32 = if r_str == "[]" { 62 } else { r_str.parse().unwrap_or(62) };
        let s = caps.get(4).map(|m| m.as_str()).unwrap_or("");
        (p, r, s.split('|').collect::<Vec<&str>>())
    } else {
        return Ok(source.to_string());
    };

    let word_re = Regex::new(r"\b\w+\b").unwrap();
    let symtab_len = symtab.len() as i64;

    let unescaped_payload = payload.replace("\\\\", "\\").replace("\\'", "'");
    let unpacked = word_re
        .replace_all(&unescaped_payload, |caps: &regex::Captures| {
            let word = &caps[0];
            let idx = unbase(word, radix);
            if idx >= 0 && idx < symtab_len {
                let replacement = symtab[idx as usize];
                if !replacement.is_empty() {
                    return replacement.to_string();
                }
            }
            word.to_string()
        })
        .into_owned();

    if unpacked.contains("eval(function(p,a,c,k,e,") && unpacked != source {
        return unpack_packer(&unpacked);
    }

    Ok(unpacked)
}

#[pyfunction]
fn fold_js_strings(source: &str) -> PyResult<String> {
    let re_dq = Regex::new(r#""([^"\\]*)"\s*\+\s*"([^"\\]*)""#).unwrap();
    let mut current = source.to_string();
    for _ in 0..8 {
        let next = re_dq.replace_all(&current, "\"$1$2\"").into_owned();
        if next == current {
            break;
        }
        current = next;
    }
    Ok(current)
}

#[pyfunction]
fn scan_stream_signatures(html: &str) -> PyResult<Vec<String>> {
    let stream_re = Regex::new(r#"https?://[^\s"'<>\\)\]]+\.(?:m3u8|mp4|mpd|mkv)(?:\?[^\s"'<>\\)\]]*)?"#).unwrap();
    let mut matches = Vec::new();
    for cap in stream_re.find_iter(html) {
        let u = cap.as_str().to_string();
        if !matches.contains(&u) {
            matches.push(u);
        }
    }
    Ok(matches)
}

#[pymodule]
fn ripper_core_rs(_py: Python, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(fast_hash64, m)?)?;
    m.add_function(wrap_pyfunction!(unpack_packer, m)?)?;
    m.add_function(wrap_pyfunction!(fold_js_strings, m)?)?;
    m.add_function(wrap_pyfunction!(scan_stream_signatures, m)?)?;
    Ok(())
}
