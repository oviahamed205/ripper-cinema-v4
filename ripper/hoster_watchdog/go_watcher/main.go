package main

import (
	"crypto/tls"
	"encoding/json"
	"fmt"
	"net/http"
	"sync"
	"time"
)

type Heartbeat struct {
	URL       string  `json:"url"`
	Status    int     `json:"status"`
	Online    bool    `json:"online"`
	LatencyMs float64 `json:"latency_ms"`
}

func pingMirror(client *http.Client, url string, ch chan<- Heartbeat, wg *sync.WaitGroup) {
	defer wg.Done()
	start := time.Now()

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		ch <- Heartbeat{URL: url, Status: 0, Online: false, LatencyMs: 0}
		return
	}
	req.Header.Set("User-Agent", "RipperGoWatcher/1.0")

	resp, err := client.Do(req)
	latency := float64(time.Since(start).Microseconds()) / 1000.0

	if err != nil {
		ch <- Heartbeat{URL: url, Status: 0, Online: false, LatencyMs: latency}
		return
	}
	defer resp.Body.Close()

	ch <- Heartbeat{
		URL:       url,
		Status:    resp.StatusCode,
		Online:    resp.StatusCode < 500,
		LatencyMs: latency,
	}
}

func main() {
	mirrors := []string{
		"https://hubcloud.cx",
		"https://gamerxyt.com",
		"https://pixeldrain.com",
		"https://gofile.io",
		"https://streamtape.com",
		"https://streamwish.to",
		"https://doodstream.com",
		"https://bunkr.is",
	}

	tr := &http.Transport{
		TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
	}
	client := &http.Client{
		Transport: tr,
		Timeout:   4 * time.Second,
	}

	ch := make(chan Heartbeat, len(mirrors))
	var wg sync.WaitGroup

	for _, m := range mirrors {
		wg.Add(1)
		go pingMirror(client, m, ch, &wg)
	}

	wg.Wait()
	close(ch)

	var results []Heartbeat
	for res := range ch {
		results = append(results, res)
	}

	out, _ := json.MarshalIndent(results, "", "  ")
	fmt.Println(string(out))
}
