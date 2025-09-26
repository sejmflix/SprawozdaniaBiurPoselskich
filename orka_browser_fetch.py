#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ORKA fetcher (Playwright, headful) — stabilna wersja:
- Każdy plik pobieramy na ODDZIELNEJ tymczasowej stronie (tabie).
- Nie używamy window.open na stronie głównej (unikamy zamknięcia głównego Page).
- Dla każdego URL: temp_page.expect_download() + temp_page.goto(url).
- Po pobraniu walidujemy nagłówek %PDF-, zapisujemy i zamykamy tylko temp_page.

Wymagania:
  python -m pip install playwright
  playwright install chromium

Użycie (najpierw mały test):
  python orka_browser_fetch.py --year 2024 --id-width 3 --start-id 1 --max-id 5 \
    --outdir sprawozdania_2024 --verbose
"""
import time
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

def build_url(year: int, sid: str) -> str:
    return f"https://orka.sejm.gov.pl/rozlicz10.nsf/lista/{year}{sid}/%24File/{year}ryczalt_{sid}.pdf"

def is_pdf_bytes(data: bytes) -> bool:
    return bool(data and data[:5] == b"%PDF-")

def save_bytes(dest: Path, data: bytes):
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(dest)

def try_single_download(ctx, url: str, dest: Path, verbose: bool, timeout_ms: int = 60000) -> bool:
    """
    Stabilne pobieranie na osobnej, tymczasowej karcie BEZ nawigacji do URL.
    - Otwieramy pustą stronę about:blank
    - Czekamy na download (expect_download)
    - W środku strony tworzymy <a download> i klikamy (JS), co uruchamia pobieranie
    - Zapisujemy plik i walidujemy, że zaczyna się od %PDF-
    """
    temp = ctx.new_page()
    try:
        # Pusta strona, żeby nie było żadnej nawigacji w momencie startu
        temp.goto("about:blank")
        if verbose:
            print(f"   [DL] temp page ready, arming download for {url}")

        with temp.expect_download(timeout=timeout_ms) as dl_info:
            # Wyzwól pobranie bez nawigowania do URL (klik w <a>)
            temp.evaluate(
                """
                (u) => {
                  const a = document.createElement('a');
                  a.href = u;
                  a.download = '';           // sugeruje 'download', zamiast otwierać viewer
                  a.target = '_self';        // zostajemy na tej samej stronie
                  document.body.appendChild(a);
                  a.click();
                  a.remove();
                }
                """,
                url,
            )

        dl = dl_info.value  # <- to zadziała dopiero, gdy przeglądarka faktycznie zacznie pobierać
        # Zapis bezpośrednio do dest
        dl.save_as(str(dest))

        data = dest.read_bytes()
        if data[:5] == b"%PDF-":
            if verbose:
                print(f"   [DL] OK ({len(data)} B)")
            return True

        if verbose:
            print(f"   [DL] not PDF ({len(data)} B) → discard")
        dest.unlink(missing_ok=True)
        return False

    except Exception as e:
        if verbose:
            print(f"   [DL] exception: {e}")
        return False
    finally:
        try:
            temp.close()
        except Exception:
            pass

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--id-width", type=int, default=3)
    ap.add_argument("--max-id", type=int, default=498)
    ap.add_argument("--start-id", type=int, default=1)
    ap.add_argument("--outdir", default="sprawozdania_2024")
    ap.add_argument("--profile-dir", default="orka_profile")
    ap.add_argument("--delay-ms", type=int, default=400)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    outdir = Path(args.outdir); outdir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=args.profile_dir,
            headless=False,
            viewport={"width": 1280, "height": 900},
            accept_downloads=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                # jeżeli masz problemy H2/QUIC, odkomentuj poniższe dwie linie:
                # "--disable-http2",
                # "--disable-quic",
            ],
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
        )
        page = ctx.new_page()
        print("Opening ORKA homepage...")
        page.goto("https://orka.sejm.gov.pl/", wait_until="domcontentloaded", timeout=60000)
        print("\n>>> Upewnij się, że w profilu jest włączone 'Always download PDFs' oraz zezwolenie na wielokrotne pobieranie.")
        print(">>> Jeśli pojawi się CAPTCHA, rozwiąż ją.")
        input(">>> ENTER aby rozpocząć batch...\n")

        ok = miss = 0
        for i in range(args.start_id, args.max_id + 1):
            sid = f"{i:0{args.id_width}d}"
            dest = outdir / f"{sid}.pdf"
            if dest.exists() and dest.stat().st_size > 200 and is_pdf_bytes(dest.read_bytes()):
                if args.verbose: print(f"[SKIP] {sid} (valid file exists)")
                continue

            url = build_url(args.year, sid)
            print(f"[TRY] {sid} → {url}")

            saved = try_single_download(ctx, url, dest, args.verbose, timeout_ms=60000)
            if not saved:
                # Domino fallback
                saved = try_single_download(ctx, url + "?Open", dest, args.verbose, timeout_ms=60000)

            if saved:
                print(f"[OK]   {sid} ({dest.stat().st_size} B)")
                ok += 1
            else:
                print(f"[MISS] {sid}")
                miss += 1

            time.sleep(args.delay_ms / 1000.0)

        print(f"\nDONE. OK:{ok} MISS:{miss}. Folder: {outdir}")
        try:
            page.close()
            ctx.close()
        except Exception:
            pass

if __name__ == "__main__":
    main()
