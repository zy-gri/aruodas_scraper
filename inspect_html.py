from pathlib import Path
from bs4 import BeautifulSoup


HTML_FILE = Path("data/raw/kaunas_rentals_manual.html")


html = HTML_FILE.read_text(encoding="utf-8", errors="ignore")
soup = BeautifulSoup(html, "lxml")

# Find first real Aruodas rental listing image
img = soup.find("img", attrs={"data-id": True, "data-objid": True})

if not img:
    raise RuntimeError("Could not find listing image")

print("LISTING ID:", f"{img.get('data-objid')}-{img.get('data-id')}")
print("ALT:", img.get("alt"))
print()

node = img

for level in range(12):
    node = node.parent

    if node is None:
        break

    text = node.get_text(" | ", strip=True)

    print("=" * 100)
    print("LEVEL:", level)
    print("TAG:", node.name)
    print("ID:", node.get("id"))
    print("CLASS:", node.get("class"))
    print("TEXT LENGTH:", len(text))
    print()
    print(text[:3500])
    print()