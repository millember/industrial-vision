package main

import (
	"crypto/sha256"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func fixture(t *testing.T) string {
	t.Helper()
	root := t.TempDir()
	rev := strings.Repeat("a", 40)
	contents := map[string]string{"REVISION": rev + "\n", "release.env": "RELEASE_ID=" + rev + "\n", "compose.server.yaml": "services: {}\n"}
	var lines []string
	for name, body := range contents {
		if err := os.WriteFile(filepath.Join(root, name), []byte(body), 0600); err != nil {
			t.Fatal(err)
		}
		lines = append(lines, fmt.Sprintf("%x  %s", sha256.Sum256([]byte(body)), name))
	}
	if err := os.WriteFile(filepath.Join(root, "SHA256SUMS"), []byte(strings.Join(lines, "\n")+"\n"), 0600); err != nil {
		t.Fatal(err)
	}
	return root
}

func TestVerifiedReleaseAndTampering(t *testing.T) {
	root := fixture(t)
	if _, err := verifyRelease(root); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "compose.server.yaml"), []byte("changed"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := verifyRelease(root); err == nil {
		t.Fatal("tampered release accepted")
	}
}

func TestManifestCannotEscapeRelease(t *testing.T) {
	for _, entry := range []string{"../outside", "/etc/passwd"} {
		t.Run(entry, func(t *testing.T) {
			root := fixture(t)
			if err := os.WriteFile(filepath.Join(root, "SHA256SUMS"), []byte(strings.Repeat("0", 64)+"  "+entry+"\n"), 0600); err != nil {
				t.Fatal(err)
			}
			if _, err := verifyRelease(root); err == nil {
				t.Fatal("escaping entry accepted")
			}
		})
	}
}

func TestForeignLockIsPreserved(t *testing.T) {
	root := t.TempDir()
	unlock, err := acquireLock(root)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := acquireLock(root); err == nil {
		t.Fatal("foreign lock accepted")
	}
	if _, err := os.Stat(filepath.Join(root, ".home-server-deploy-lock")); err != nil {
		t.Fatal(err)
	}
	if err := unlock(); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(root, ".home-server-deploy-lock")); !os.IsNotExist(err) {
		t.Fatal("own lock was not removed")
	}
}

func TestDatabaseSecretsPersistAndArePrivate(t *testing.T) {
	base := t.TempDir()
	env, err := prepareDatabase(base)
	if err != nil {
		t.Fatal(err)
	}
	before, err := os.ReadFile(env)
	if err != nil {
		t.Fatal(err)
	}
	info, err := os.Stat(env)
	if err != nil {
		t.Fatal(err)
	}
	if info.Mode().Perm() != 0600 {
		t.Fatal("environment permissions are not private")
	}
	_, err = prepareDatabase(base)
	if err != nil {
		t.Fatal(err)
	}
	after, err := os.ReadFile(env)
	if err != nil {
		t.Fatal(err)
	}
	if string(before) != string(after) {
		t.Fatal("credentials rotated on repeated startup")
	}
	sql, err := os.ReadFile(filepath.Join(filepath.Dir(env), "init.sql"))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(sql), "NOSUPERUSER NOCREATEDB NOCREATEROLE") {
		t.Fatal("runtime DB user has excessive privilege")
	}
}
