import urllib.request
import time

def benchmark_stream(name, url, sample_seconds=6.0):
    print(f"Testing: [{name}] for {sample_seconds} seconds0...")
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        t0 = time.perf_counter()
        total_bytes = 0
        with urllib.request.urlopen(req, timeout=12) as resp:
            while True:
                chunk = resp.read(131072)
                if not chunk:
                    break
                total_bytes += len(chunk)
                elapsed = time.perf_counter() - t0
                if elapsed >= sample_seconds:
                    break
        speed = (total_bytes / elapsed) / (1024 * 1024)
        mb = total_bytes / (1024 * 1024)
        print(f"  --> {name}: {speed:.2f} MB/s ({mb:.2f} MB in {elapsed:.2f}s)")
        return {'mirror': name, 'speed_mb_s': round(speed, 2), 'bytes': total_bytes}
    except Exception as e:
        print(f"  --> {name} Error: {e}")
        return {'mirror': name, 'speed_mb_s': 0.0, 'bytes': 0}

if __name__ == '__main__':
    targets = [
        ("Cloudflare R2 Direct CDN (10Gbps)", "https://pub-2db09ba4f85e4d5987aee376ed3d1fee.r2.dev/28ea7f7d4a2ed6d873e1587434a52d97?token=1788711673"),
        ("Direct PixelDrain CDN (480p)", "https://pixeldrain.com/api/file/wmv2g3Ai"),
        ("Direct PixelDrain CDN (1080p)", "https://pixeldrain.com/api/file/gxNcapSn"),
    ]
    results = [benchmark_stream(n, u) for n, u in targets]
    best = max(results, key=lambda x: x['speed_mb_s'])
    print("")
    print("==========================================================")
    print(f"\nWINNER (HIGHEST DOWNLOAD SPEED): [{best['mirror']}] @ {best['speed_mb_s']} MB/s\n")
    print("==========================================================")
