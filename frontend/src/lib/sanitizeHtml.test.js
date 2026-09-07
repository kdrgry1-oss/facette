import { sanitizeHtml } from "./sanitizeHtml";

describe("sanitizeHtml", () => {
  test("removes executable elements and event handlers", () => {
    const html = '<p onclick="alert(1)">Merhaba</p><script>window.pwned=1</script><img src="x" onerror="alert(2)">';
    const clean = sanitizeHtml(html);
    expect(clean).toContain("Merhaba");
    expect(clean).not.toMatch(/script|onclick|onerror/i);
  });

  test("blocks obfuscated executable URLs", () => {
    const clean = sanitizeHtml('<a href="java\tscript:alert(1)">Tıkla</a><img src="data:image/svg+xml,x">');
    expect(clean).not.toMatch(/javascript|data:image\/svg/i);
  });

  test("adds reverse-tabnabbing protection", () => {
    expect(sanitizeHtml('<a href="https://example.com" target="_blank">A</a>'))
      .toContain('rel="noopener noreferrer"');
  });

  test("allows safe email inline styles but drops network-capable styles", () => {
    expect(sanitizeHtml('<p style="color:red">A</p>', { allowStyle: true }))
      .toContain('style="color:red"');
    expect(sanitizeHtml('<p style="background:url(https://evil.test/x)">A</p>', { allowStyle: true }))
      .not.toContain("style=");
  });
});
