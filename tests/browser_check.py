"""Run against a local static server: python tests/browser_check.py [base-url]."""
import sys
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright

base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8123"

with sync_playwright() as pw, tempfile.TemporaryDirectory() as temp:
    browser = pw.chromium.launch(executable_path="/usr/bin/chromium", args=["--no-sandbox"])
    context = browser.new_context(accept_downloads=True, viewport={"width": 1360, "height": 1000})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(base)

    def set_value(selector, value, event="input"):
        page.locator(selector).evaluate("(el, a) => { el.value = a.value; el.dispatchEvent(new Event(a.event, {bubbles:true})); }", {"value": str(value), "event": event})
        page.wait_for_function("!pending")

    assert page.locator("#pixelCount").inner_text() == "1,024"
    assert page.locator("#dataSize").inner_text() == "3,072 B"
    # Known RGB input validates center sampling, integer quantization and code values.
    page.evaluate("ctx.fillStyle='rgb(127,128,255)';ctx.fillRect(0,0,512,512);render()")
    page.locator('[data-step="quantization"]').click()
    assert page.locator("#bitCount").inner_text() == "6 bit"
    assert page.locator("#dataSize").inner_text() == "768 B"
    assert page.evaluate("Array.from(frame.codes.slice(0,3))") == [1, 2, 3]
    assert page.evaluate("Array.from(frame.processed.data.slice(0,4))") == [85, 170, 255, 255]
    before = page.evaluate("result.toDataURL()")
    page.locator('[data-step="encoding"]').click()
    assert page.evaluate("result.toDataURL()") == before
    assert page.locator("#codeRows code").all_text_contents() == ["01", "10", "11"]
    page.locator("#result").click(position={"x": 100, "y": 100})
    previous = page.evaluate("selected.x")
    page.keyboard.press("ArrowRight")
    assert page.evaluate("selected.x") == previous + 1

    page.select_option("#mode", "gray")
    set_value("#bits", 1)
    assert page.evaluate("frame.codes[0]") == 1
    assert page.locator("#bitCount").inner_text() == "1 bit"
    set_value("#pixels", 2)
    assert page.locator("#dataSize").inner_text() == "2 B"

    # Same pixels: resolution affects printed size, not bytes or image content.
    fixed = page.evaluate("({bytes:document.querySelector('#dataSize').textContent,image:result.toDataURL(),n:frame.n})")
    set_value("#ppi", 128)
    assert page.evaluate("frame.n") == fixed["n"]
    assert page.locator("#dataSize").inner_text() == fixed["bytes"]
    assert page.evaluate("result.toDataURL()") == fixed["image"]
    assert "0.08 cm" in page.locator("#resolutionNumbers").inner_text()
    # Same print size: double ppi doubles each dimension and quadruples data.
    page.select_option("#resolutionBasis", "print")
    set_value("#printSize", "2.54")
    set_value("#ppi", 32)
    assert page.evaluate("frame.n") == 32
    assert page.locator("#dataSize").inner_text() == "128 B"
    set_value("#ppi", 64)
    assert page.evaluate("frame.n") == 64
    assert page.locator("#dataSize").inner_text() == "512 B"
    assert page.locator("#pixels").is_disabled()
    set_value("#printSize", ".5")
    set_value("#ppi", 8)
    assert page.evaluate("frame.n") == 2
    assert page.locator("#dataSize").inner_text() == "0.5 B"

    # Actual pointer drawing, undo and clear restore source pixel data.
    page.select_option("#resolutionBasis", "pixels")
    page.select_option("#sample", "blank")
    page.locator("#loadSample").click()
    source_before = page.evaluate("source.toDataURL()")
    box = page.locator("#original").bounding_box()
    page.mouse.move(box["x"] + 50, box["y"] + 50)
    page.mouse.down()
    page.mouse.move(box["x"] + 130, box["y"] + 130, steps=8)
    page.mouse.up()
    assert page.evaluate("source.toDataURL()") != source_before
    page.locator("#undo").click()
    assert page.evaluate("source.toDataURL()") == source_before
    page.locator("#clear").click()
    assert page.evaluate("Array.from(ctx.getImageData(1,1,1,1).data)") == [255, 255, 255, 255]

    with page.expect_download() as save:
        page.locator("#savePng").click()
    png_path = Path(temp) / "image.png"
    save.value.save_as(png_path)
    assert png_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    with page.expect_download() as save:
        page.locator("#saveCodes").click()
    text_path = Path(temp) / "bits.txt"
    save.value.save_as(text_path)
    assert "1 | 1 | 1 | 1" in text_path.read_text()
    with page.expect_download() as save:
        page.locator("#downloadApp").click()
    html_path = Path(temp) / "app.html"
    save.value.save_as(html_path)
    context.set_offline(True)
    offline = context.new_page()
    # Load the downloaded bytes directly; managed browsers can prohibit file:// URLs.
    offline.set_content(html_path.read_text(), wait_until="load")
    assert offline.title() == "画像のデジタル化君２"
    assert offline.locator("#pixelCount").inner_text() == "1,024"
    offline.locator('[data-step="encoding"]').click()
    assert offline.locator("#inspector").is_visible()
    context.set_offline(False)

    page.goto(base + "/download.html")
    page.on("dialog", lambda dialog: dialog.accept())
    with page.expect_download() as save:
        page.locator("#download").click()
    assert save.value.suggested_filename == "img_digital_kun2.html"
    # Narrow phone and tablet layouts must remain within the viewport.
    page.goto(base)
    for width in [375, 640, 768, 1024]:
        page.set_viewport_size({"width": width, "height": 900})
        page.locator('[data-step="encoding"]').click()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), width
    touch = browser.new_context(viewport={"width": 768, "height": 1024}, has_touch=True)
    tablet = touch.new_page()
    tablet.goto(base)
    old = tablet.evaluate("source.toDataURL()")
    rect = tablet.locator("#original").bounding_box()
    tablet.touchscreen.tap(rect["x"] + 20, rect["y"] + 20)
    assert tablet.evaluate("source.toDataURL()") != old
    assert not errors, errors
    print("PASS: sampling, quantization, binary encoding, resolution, drawing/undo, downloads, offline HTML, responsive layouts and touch")
    browser.close()
