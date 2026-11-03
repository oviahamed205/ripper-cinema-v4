//! High-throughput AES-128-CBC Click'n'Load (CNL2) Decryptor in Rust.

use aes::Aes128;
use cbc::cipher::{block_padding::Pkcs7, BlockDecryptMut, KeyIvInit};
use base64::prelude::*;
use hex::FromHex;
use regex::Regex;

type Aes128CbcDec = cbc::Decryptor<Aes128>;

/// Extracts 16-byte key from jk javascript string
pub fn extract_key(jk_str: &str) -> Result<[u8; 16], String> {
    let re_hex = Regex::new(r#"['"]([0-9a-fA-F]{32})['"]"#).map_err(|e| e.to_string())?;
    if let Some(caps) = re_hex.captures(jk_str) {
        if let Some(matched) = caps.get(1) {
            let hex_str = matched.as_str();
            let bytes = <[u8; 16]>::from_hex(hex_str).map_err(|e| e.to_string())?;
            return Ok(bytes);
        }
    }

    let re_ascii = Regex::new(r#"return\s*['"]([^'"]{16})['"]"#).map_err(|e| e.to_string())?;
    if let Some(caps) = re_ascii.captures(jk_str) {
        if let Some(matched) = caps.get(1) {
            let mut key = [0u8; 16];
            let b = matched.as_str().as_bytes();
            if b.len() == 16 {
                key.copy_from_slice(b);
                return Ok(key);
            }
        }
    }

    Err(format!("Could not extract 16-byte key from jk string: {}", jk_str))
}

/// Decrypts CNL2 payload in Rust and extracts clean URLs
pub fn decrypt_cnl2(crypted_b64: &str, jk_str: &str) -> Result<Vec<String>, String> {
    let key = extract_key(jk_str)?;
    let iv = key; // IV is identical to Key in CNL2 specification

    let clean_b64 = crypted_b64.replace(' ', "+");
    let mut ciphertext = BASE64_STANDARD.decode(clean_b64.trim())
        .map_err(|e| format!("Base64 decode failure: {}", e))?;

    let cipher = Aes128CbcDec::new(&key.into(), &iv.into());
    let decrypted_slice = cipher.decrypt_padded_mut::<Pkcs7>(&mut ciphertext)
        .map_err(|e| format!("AES-CBC decryption failure: {:?}", e))?;

    let plain_str = String::from_utf8_lossy(decrypted_slice);
    let urls: Vec<String> = plain_str
        .lines()
        .map(|l| l.trim().to_string())
        .filter(|l| l.starts_with("http://") || l.starts_with("https://"))
        .collect();

    Ok(urls)
}
