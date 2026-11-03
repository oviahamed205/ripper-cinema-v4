use regex::Regex;
use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize, Debug)]
pub struct FastParsedQuery {
    pub title: String,
    pub year: Option<u32>,
    pub quality: String,
}

pub fn fast_parse_query(input: &str) -> FastParsedQuery {
    let year_re = Regex::new(r"\b(19\d{2}|20\d{2})\b").unwrap();
    let quality_re = Regex::new(r"(?i)\b(2160p|1080p|720p|480p|4k)\b").unwrap();

    let year = year_re
        .find(input)
        .and_then(|m| m.as_str().parse::<u32>().ok());

    let quality = quality_re
        .find(input)
        .map(|m| m.as_str().to_uppercase())
        .unwrap_or_else(|| "ANY".to_string());

    FastParsedQuery {
        title: input.trim().to_string(),
        year,
        quality,
    }
}
