use regex::Regex;

pub struct ErrorPatternMatcher {
    patterns: Vec<(Regex, &'static str, &'static str)>,
}

impl ErrorPatternMatcher {
    pub fn new() -> Self {
        let patterns = vec![
            (Regex::new(r"XMLParsedAsHTMLWarning").unwrap(), "XML_MISMATCH", "Use XML parser or regex loc extractor"),
            (Regex::new(r"403 Forbidden|Cloudflare|CF-RAY").unwrap(), "CLOUDFLARE_BLOCK", "Rotate TLS and bypass headers"),
            (Regex::new(r"429 Too Many Requests").unwrap(), "RATE_LIMIT", "Backoff with exponential jitter"),
            (Regex::new(r"UnicodeDecodeError").unwrap(), "ENCODING_ERROR", "Fallback to latin-1 / replace mode"),
            (Regex::new(r"JSONDecodeError").unwrap(), "MALFORMED_JSON", "Strip markdown fences and auto-repair JSON"),
            (Regex::new(r"ConnectTimeout|NameResolutionError").unwrap(), "NETWORK_DOWN", "Switch to DNS-over-HTTPS or retry mirror"),
        ];
        Self { patterns }
    }

    pub fn fast_scan(&self, line: &str) -> Option<(&'static str, &'static str)> {
        for (re, kind, remedy) in &self.patterns {
            if re.is_match(line) {
                return Some((*kind, *remedy));
            }
        }
        None
    }
}
