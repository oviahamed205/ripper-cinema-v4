// Click'n'Load 2 (CNL2) Standalone Port 9666 HTTP Daemon in Go.
// Zero external dependencies; uses Go standard library net/http and crypto/aes.

package main

import (
	"crypto/aes"
	"crypto/cipher"
	"encoding/base64"
	"encoding/hex"
	"fmt"
	"log"
	"net/http"
	"regexp"
	"strings"
)

const (
	Port = ":9666"
)

var (
	hexKeyRegex = regexp.MustCompile(`['"]([0-9a-fA-F]{32})['"]`)
)

func handleCrossDomain(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "text/xml")
	w.Header().Set("Access-Control-Allow-Origin", "*")
	xml := `<?xml version="1.0"?>
<!DOCTYPE cross-domain-policy SYSTEM "http://www.macromedia.com/xml/dtds/cross-domain-policy.dtd">
<cross-domain-policy>
  <allow-access-from domain="*" />
</cross-domain-policy>`
	fmt.Fprint(w, xml)
}

func handleCheck(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Access-Control-Allow-Origin", "*")
	fmt.Fprint(w, "JDownloader")
}

func extractKey(jk string) ([]byte, error) {
	matches := hexKeyRegex.FindStringSubmatch(jk)
	if len(matches) > 1 {
		return hex.DecodeString(matches[1])
	}
	return nil, fmt.Errorf("could not extract hex key from jk script")
}

func decryptCNL2(cryptedB64, jk string) ([]string, error) {
	key, err := extractKey(jk)
	if err != nil {
		return nil, err
	}
	iv := key

	cleanB64 := strings.ReplaceAll(cryptedB64, " ", "+")
	ciphertext, err := base64.StdEncoding.DecodeString(strings.TrimSpace(cleanB64))
	if err != nil {
		return nil, fmt.Errorf("base64 decode failure: %w", err)
	}

	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, fmt.Errorf("cipher init failure: %w", err)
	}

	if len(ciphertext)%aes.BlockSize != 0 {
		return nil, fmt.Errorf("ciphertext is not a multiple of the block size")
	}

	mode := cipher.NewCBCDecrypter(block, iv)
	plaintext := make([]byte, len(ciphertext))
	mode.CryptBlocks(plaintext, ciphertext)

	// Simple PKCS7 unpad
	if len(plaintext) > 0 {
		padLen := int(plaintext[len(plaintext)-1])
		if padLen > 0 && padLen <= aes.BlockSize {
			plaintext = plaintext[:len(plaintext)-padLen]
		}
	}

	raw := string(plaintext)
	lines := strings.Split(raw, "\n")
	var urls []string
	for _, line := range lines {
		l := strings.TrimSpace(line)
		if strings.HasPrefix(l, "http://") || strings.HasPrefix(l, "https://") {
			urls = append(urls, l)
		}
	}

	return urls, nil
}

func handleAddCrypted2(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Access-Control-Allow-Origin", "*")
	if r.Method == http.MethodOptions {
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
		w.WriteHeader(http.StatusOK)
		return
	}

	if err := r.ParseForm(); err != nil {
		http.Error(w, "bad request", http.StatusBadRequest)
		return
	}

	crypted := r.FormValue("crypted")
	jk := r.FormValue("jk")

	if crypted == "" || jk == "" {
		http.Error(w, "missing crypted or jk parameter", http.StatusBadRequest)
		return
	}

	urls, err := decryptCNL2(crypted, jk)
	if err != nil {
		log.Printf("CNL2 decryption error: %v\n", err)
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	log.Printf("Successfully decrypted %d URLs from Click'n'Load payload:\n", len(urls))
	for _, u := range urls {
		fmt.Printf(" [UNLOCKED] %s\n", u)
	}

	fmt.Fprint(w, "success\r\n")
}

func main() {
	http.HandleFunc("/crossdomain.xml", handleCrossDomain)
	http.HandleFunc("/flash/", handleCheck)
	http.HandleFunc("/flash/check", handleCheck)
	http.HandleFunc("/flash/addcrypted2", handleAddCrypted2)

	log.Printf("⚡ Ripper CNL2 Go Daemon listening on http://127.0.0.1%s ...\n", Port)
	if err := http.ListenAndServe(Port, nil); err != nil {
		log.Fatalf("Server failed: %v", err)
	}
}
