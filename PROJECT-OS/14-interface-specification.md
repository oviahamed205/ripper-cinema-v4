# INTERFACE SPECIFICATION

## CLI Interface
Executable: `unshorten` / `unshorten-cli`

### Usage:
```
unshorten [OPTIONS] [URLS]...
```

### Options:
- `-i, --interactive`: Launch interactive visual terminal dashboard.
- `-s, --search TEXT`: Search movies & series by name across CineFreak, KMmovies, Katworld.
- `-w, --watch`: 1-Click Instant Watch: auto-resolve Cloud and launch player (e.g. PotPlayer).
- `-f, --file PATH`: Load and unshorten list of URLs from file (.txt, .csv, .md).
- `-o, --output PATH`: Export resolved results to file (.json, .csv, .md).
- `-p, --paste TEXT`: Raw HTML snippet containing download-links-div / episode-grid.
- `--media`: Extract & deep-unshorten media/episode grid from page URL or pasted HTML.
- `--simulate, -sim`: Run 100-Run Iterative Simulation & System Diagnostic Suite.
- `-c, --concurrency INTEGER`: Number of parallel worker streams for batch mode (default: 10).
- `-m, --max-hops INTEGER`: Maximum number of redirect hops before stopping (default: 15).
- `-t, --timeout FLOAT`: HTTP connection timeout in seconds (default: 5.0s).
- `--json`: Output results in machine-readable raw JSON format.
- `--deep`: Include detailed HTTP headers and security breakdown.
- `-h, --help`: Show help message and exit.
