use serde::{Deserialize, Serialize};
use std::time::Instant;
use futures::future::join_all;

#[derive(Debug, Serialize, Deserialize)]
struct ProbeResult {
    url: String,
    online: bool,
    status_code: u16,
    latency_ms: f64,
}

async fn check_mirror(client: &reqwest::Client, url: &str) -> ProbeResult {
    let start = Instant::now();
    match client.get(url).timeout(std::time::Duration::from_secs(4)).send().await {
        Ok(resp) => {
            let status = resp.status().as_u16();
            let latency = start.elapsed().as_secs_f64() * 1000.0;
            ProbeResult {
                url: url.to_string(),
                online: status < 500,
                status_code: status,
                latency_ms: latency,
            }
        }
        Err(_) => ProbeResult {
            url: url.to_string(),
            online: false,
            status_code: 0,
            latency_ms: start.elapsed().as_secs_f64() * 1000.0,
        },
    }
}

#[tokio::main]
async fn main() {
    let mirrors = vec![
        "https://hubcloud.cx",
        "https://hubcloud.fit",
        "https://gamerxyt.com",
        "https://pixeldrain.com",
        "https://gofile.io",
        "https://streamtape.com",
        "https://streamwish.to",
        "https://doodstream.com",
        "https://bunkr.is",
    ];

    let client = reqwest::Client::builder()
        .user_agent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) RipperRustProbe/1.0")
        .danger_accept_invalid_certs(true)
        .build()
        .unwrap();

    let tasks: Vec<_> = mirrors.iter().map(|url| check_mirror(&client, url)).collect();
    let results = join_all(tasks).await;

    let json_output = serde_json::to_string_pretty(&results).unwrap();
    println!("{}", json_output);
}
