// start builds and starts only the prepared Industrial Vision release.
package main

import (
	"bufio"
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"
	"time"
)

func acquireLock(base string) (func() error, error) {
	lock := filepath.Join(base, ".home-server-deploy-lock")
	if err := os.Mkdir(lock, 0700); err != nil {
		return nil, fmt.Errorf("deployment lock is occupied or unavailable: %w", err)
	}
	return func() error { return os.Remove(lock) }, nil
}

func verifyRelease(root string) (string, error) {
	revision, err := os.ReadFile(filepath.Join(root, "REVISION"))
	if err != nil {
		return "", err
	}
	rev := strings.TrimSpace(string(revision))
	if decoded, err := hex.DecodeString(rev); err != nil || len(decoded) != 20 {
		return "", errors.New("invalid REVISION")
	}
	manifest, err := os.Open(filepath.Join(root, "SHA256SUMS"))
	if err != nil {
		return "", err
	}
	defer manifest.Close()
	scanner := bufio.NewScanner(manifest)
	count := 0
	for scanner.Scan() {
		checksum, name, ok := strings.Cut(scanner.Text(), "  ")
		if !ok || len(checksum) != 64 || name == "" || filepath.IsAbs(name) || filepath.Clean(name) != name || strings.HasPrefix(name, "../") {
			return "", errors.New("invalid checksum manifest entry")
		}
		path := filepath.Join(root, name)
		// No symlink may redirect a manifest entry outside the prepared release.
		resolved, err := filepath.EvalSymlinks(path)
		if err != nil {
			return "", err
		}
		relative, err := filepath.Rel(root, resolved)
		if err != nil || relative == ".." || strings.HasPrefix(relative, "../") {
			return "", errors.New("manifest path escapes release")
		}
		file, err := os.Open(path)
		if err != nil {
			return "", err
		}
		hash := sha256.New()
		_, copyErr := io.Copy(hash, file)
		closeErr := file.Close()
		if copyErr != nil {
			return "", copyErr
		}
		if closeErr != nil {
			return "", closeErr
		}
		if hex.EncodeToString(hash.Sum(nil)) != checksum {
			return "", fmt.Errorf("checksum mismatch: %s", name)
		}
		count++
	}
	if err := scanner.Err(); err != nil {
		return "", err
	}
	if count == 0 {
		return "", errors.New("empty manifest")
	}
	env, err := os.ReadFile(filepath.Join(root, "release.env"))
	if err != nil {
		return "", err
	}
	if strings.TrimSpace(string(env)) != "RELEASE_ID="+rev {
		return "", errors.New("release.env does not match REVISION")
	}
	return rev, nil
}

func prepareDatabase(base string) (string, error) {
	dir := filepath.Join(base, "industrial-vision", "private")
	if err := os.MkdirAll(dir, 0700); err != nil {
		return "", err
	}
	env := filepath.Join(dir, "database.env")
	if _, err := os.Stat(env); err == nil {
		if _, err := os.Stat(filepath.Join(dir, "init.sql")); err != nil {
			return "", err
		}
		return env, nil
	} else if !os.IsNotExist(err) {
		return "", err
	}
	if _, err := os.Stat(filepath.Join(dir, "init.sql")); !os.IsNotExist(err) {
		return "", errors.New("partial database configuration requires inspection")
	}
	random := func() (string, error) {
		data := make([]byte, 32)
		_, err := rand.Read(data)
		return hex.EncodeToString(data), err
	}
	admin, err := random()
	if err != nil {
		return "", err
	}
	app, err := random()
	if err != nil {
		return "", err
	}
	sql := "CREATE ROLE iv_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD '" + app + "';\nCREATE DATABASE industrial_vision OWNER iv_app;\n"
	if err := os.WriteFile(filepath.Join(dir, "init.sql"), []byte(sql), 0644); err != nil {
		return "", err
	}
	if err := os.Chmod(filepath.Join(dir, "init.sql"), 0644); err != nil {
		return "", err
	}
	body := "POSTGRES_PASSWORD=" + admin + "\nAPP_DATABASE_PASSWORD=" + app + "\nIV_PRIVATE_DIR=" + dir + "\n"
	if err := os.WriteFile(env, []byte(body), 0600); err != nil {
		return "", err
	}
	return env, nil
}

func run(ctx context.Context) (code int) {
	if os.Geteuid() != 0 {
		fmt.Fprintln(os.Stderr, "Run with sudo.")
		return 1
	}
	base := "/home/serveradmin/services"
	release, err := filepath.EvalSymlinks(filepath.Join(base, "industrial-vision", "pending"))
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	releases := filepath.Join(base, "industrial-vision", "releases")
	if filepath.Dir(release) != releases {
		fmt.Fprintln(os.Stderr, "pending must point directly into releases")
		return 1
	}
	unlock, err := acquireLock(base)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	defer func() {
		if err := unlock(); err != nil {
			fmt.Fprintln(os.Stderr, "Cannot release own deployment lock:", err)
			if code == 0 {
				code = 1
			}
		}
	}()
	revision, err := verifyRelease(release)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	if filepath.Base(release) != revision {
		fmt.Fprintln(os.Stderr, "release directory does not match REVISION")
		return 1
	}
	fmt.Println("Verified Industrial Vision release:", revision)
	privateEnv, err := prepareDatabase(base)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	args := []string{"compose", "-p", "industrial-vision", "--env-file", privateEnv, "--env-file", "release.env", "-f", "compose.server.yaml"}
	actions := [][]string{{"config", "--quiet"}, {"up", "-d", "--build", "--wait", "--wait-timeout", "90"}}
	if len(os.Args) > 1 {
		if len(os.Args) != 2 || (os.Args[1] != "admin" && os.Args[1] != "demo") {
			fmt.Fprintln(os.Stderr, "Usage: start [admin|demo]")
			return 2
		}
		actions = [][]string{{"exec", "backend", "python", "-m", "app.manage", "create-admin", "--login", "niyaz"}}
		if os.Args[1] == "demo" {
			actions = [][]string{{"exec", "backend", "python", "-m", "app.manage", "seed-demo"}}
		}
	}
	for _, action := range actions {
		command := exec.CommandContext(ctx, "docker", append(append([]string{}, args...), action...)...)
		command.Dir = release
		command.Stdin, command.Stdout, command.Stderr = os.Stdin, os.Stdout, os.Stderr
		command.WaitDelay = 5 * time.Second
		if err := command.Run(); err != nil {
			fmt.Fprintln(os.Stderr, "Docker command failed:", err)
			if ctx.Err() != nil {
				fmt.Fprintln(os.Stderr, ctx.Err())
			}
			var exit *exec.ExitError
			if errors.As(err, &exit) && exit.ExitCode() > 0 {
				return exit.ExitCode()
			}
			return 1
		}
	}
	fmt.Println("Industrial Vision command completed successfully.")
	return 0
}

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	ctx, cancel := context.WithTimeout(ctx, 10*time.Minute)
	defer cancel()
	os.Exit(run(ctx))
}
