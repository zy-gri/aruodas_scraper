from src.scraper import fetch_page


def main():
    try:
        result = fetch_page()

        print()
        print("=== ARUODAS FETCH RESULT ===")
        print(f"Status:       {result.status_code}")
        print(f"Time:         {result.elapsed_seconds:.2f}s")
        print(f"Bytes:        {result.content_length:,}")
        print(f"Content-Type: {result.content_type}")
        print(f"SHA256:       {result.sha256}")
        print(f"HTML:         {result.html_path}")
        print(f"Metadata:     {result.metadata_path}")

        if result.status_code == 200:
            print()
            print("[OK] Server returned HTTP 200.")
        elif result.status_code in (403, 429):
            print()
            print("[BLOCKED] Aruodas rejected or rate-limited the request.")
        else:
            print()
            print(f"[WARNING] Unexpected HTTP status: {result.status_code}")

    except Exception as exc:
        print()
        print("[ERROR]")
        print(type(exc).__name__, str(exc))
        raise


if __name__ == "__main__":
    main()