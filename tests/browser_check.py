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
    assert page.locator("#bitStat").is_hidden()
    assert page.locator("#dataStat").is_hidden()
    assert page.locator("#color").input_value() == "#000000"
    assert page.locator("#sample").count() == 0
    assert page.evaluate("Array.from(ctx.getImageData(20,20,1,1).data)") == [255, 255, 255, 255]
    assert "px" not in page.locator(".comparison article").first.inner_text()
    page.locator('[data-step="quantization"]').click()
    assert page.locator("#bitCount").inner_text() == "24 bit"
    assert page.locator("#dataSize").inner_text() == "3,072 B"
    page.select_option("#mode", "gray")
    assert page.locator("#bitCount").inner_text() == "8 bit"
    assert page.locator("#dataSize").inner_text() == "1,024 B"
    page.select_option("#mode", "mono")
    assert page.locator("#bitCount").inner_text() == "1 bit"
    assert page.locator("#bits").is_disabled()
    assert page.locator("#dataSize").inner_text() == "128 B"
    assert page.evaluate("new Set(frame.codes).size") == 1
    assert page.locator("#bits").input_value() == "1"
    page.evaluate("ctx.fillStyle='rgb(127,127,127)';ctx.fillRect(0,0,512,512);render()")
    assert page.evaluate("frame.codes[0]") == 0
    assert page.evaluate("Array.from(frame.processed.data.slice(0,4))") == [0, 0, 0, 255]
    page.evaluate("ctx.fillStyle='rgb(128,128,128)';ctx.fillRect(0,0,512,512);render()")
    assert page.evaluate("frame.codes[0]") == 1
    assert page.evaluate("Array.from(frame.processed.data.slice(0,4))") == [255, 255, 255, 255]
    page.select_option("#mode", "rgb")
    assert page.locator("#bits").input_value() == "8"
    assert page.locator("#bits").is_enabled()
    page.locator('[data-step="sampling"]').click()
    page.select_option("#mode", "gray")
    assert page.locator('[data-step="quantization"]').get_attribute("aria-pressed") == "true"
    assert page.locator("#bitCount").inner_text() == "8 bit"
    page.select_option("#mode", "rgb")
    set_value("#bits", 2)
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
    assert page.locator("#pixelDialog").is_hidden()
    assert page.locator("#totalDigits").inner_text() == "6,144 桁"
    full = page.locator("#fullCodes").input_value()
    assert full.splitlines() == ["011011" * 32] * 32
    assert len(full.replace("\n", "")) == 6144
    context.grant_permissions(["clipboard-read", "clipboard-write"])
    page.locator("#copyCodes").click()
    page.wait_for_function("document.querySelector('#copyStatus').textContent.includes('コピーしました')")
    assert page.evaluate("navigator.clipboard.readText()") == full
    assert page.locator("#fullCodes").evaluate("el => el.scrollWidth > el.clientWidth && el.scrollHeight > el.clientHeight")
    page.locator("#result").click()
    assert page.locator("#pixelDialog").is_visible()
    assert page.locator("#codeRows code").all_text_contents() == ["01", "10", "11"]
    page.locator("#closePixel").click()
    page.locator("#result").click(position={"x": 20, "y": 20})
    previous = page.evaluate("selected.x")
    page.keyboard.press("ArrowRight")
    assert page.evaluate("selected.x") == previous + 1
    page.locator("#closePixel").click()

    page.select_option("#mode", "gray")
    set_value("#bits", 1)
    assert page.evaluate("frame.codes[0]") == 1
    assert page.locator("#bitCount").inner_text() == "1 bit"
    set_value("#pixels", 2)
    assert page.locator("#dataSize").inner_text() == "2 B"

    assert page.locator("#samplingControls").evaluate("el=>el.classList.contains('is-active')")
    page.locator('[data-step="encoding"]').click()
    assert page.locator("#totalDigits").inner_text() == "16 桁"
    assert len(page.locator("#fullCodes").input_value().replace("\n", "")) == 16
    # A single print-size control leaves pixels and encoded data unchanged.
    fixed = page.evaluate("({bytes:document.querySelector('#dataSize').textContent,image:result.toDataURL(),n:frame.n})")
    page.locator("#tab-resolution").click()
    assert page.locator("#resolutionView input").count() == 1
    assert page.locator("#ppiValue").inner_text() == "4 ppi"
    page.locator('[data-size="5.08"]').click()
    assert page.evaluate("frame.n") == fixed["n"]
    assert page.locator("#dataSize").inner_text() == fixed["bytes"]
    assert page.evaluate("result.toDataURL()") == fixed["image"]
    assert page.locator("#ppiValue").inner_text() == "2 ppi"
    side = page.locator("#paper").bounding_box()["width"]
    page.locator('[data-size="10.16"]').click()
    assert page.locator("#ppiValue").inner_text() == "1 ppi"
    assert abs(page.locator("#paper").bounding_box()["width"] - side * 2) < 1
    assert page.evaluate("frame.n") == fixed["n"]
    assert page.locator("#dataSize").inner_text() == fixed["bytes"]

    # Actual pointer drawing, undo and clear restore source pixel data.
    page.locator("#tab-drawing").click()
    page.locator("#clear").click()
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

    page.locator("#tab-guide").click()
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
    assert offline.locator("#encodingPanel").is_visible()
    offline.locator("#result").click()
    assert offline.locator("#pixelDialog").is_visible()
    context.set_offline(False)

    page.locator("#tab-drawing").click()
    set_value("#pixels", 8)
    page.select_option("#mode", "rgb")
    set_value("#bits", 8)
    page.locator('[data-step="encoding"]').click()
    assert page.locator("#totalDigits").inner_text() == "1,572,864 桁"
    assert len(page.locator("#fullCodes").input_value().replace("\n", "")) == 1_572_864

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
        assert page.locator("#fullCodes").is_visible()
    for width, height in [(1024, 768), (1180, 820), (1194, 834), (1366, 1024), (1024, 680)]:
        page.set_viewport_size({"width": width, "height": height})
        page.locator("#tab-drawing").click()
        page.locator('[data-step="quantization"]').click()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (width, height)
        bottom = page.locator(".settings").bounding_box()
        assert bottom["y"] + bottom["height"] <= height, (width, height, bottom)
        page.locator('[data-step="encoding"]').click()
        code_box = page.locator("#fullCodes").bounding_box()
        assert code_box["y"] + code_box["height"] <= height, (width, height, code_box)
        assert page.locator("#pixelDialog").is_hidden()
        for view in ["resolution", "guide", "drawing"]:
            page.locator("#tab-" + view).click()
            assert page.locator("#" + view + "View").is_visible()
        page.locator("#tab-drawing").focus()
        page.keyboard.press("ArrowRight")
        assert page.locator("#resolutionView").is_visible()
        page.locator("#tab-drawing").click()
    touch = browser.new_context(viewport={"width": 1024, "height": 768}, has_touch=True)
    tablet = touch.new_page()
    tablet.goto(base)
    old = tablet.evaluate("source.toDataURL()")
    rect = tablet.locator("#original").bounding_box()
    tablet.touchscreen.tap(rect["x"] + 20, rect["y"] + 20)
    assert tablet.evaluate("source.toDataURL()") != old
    assert not errors, errors
    print("PASS: sampling, quantization, binary encoding, resolution, drawing/undo, downloads, offline HTML, whole-image binary digits and clipboard, pixel popups, simple resolution, iPad landscape tabs and touch")
    browser.close()
