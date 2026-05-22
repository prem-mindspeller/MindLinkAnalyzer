const { chromium } = require('playwright');

async function main() {
  const browser = await chromium.launch({ headless: true });
  const viewports = [
    { width: 1280, height: 720 },
    { width: 390, height: 844 },
  ];
  const results = [];

  for (const viewport of viewports) {
    const page = await browser.newPage({ viewport });
    await page.goto('http://127.0.0.1:5174', { waitUntil: 'networkidle' });
    await page.waitForTimeout(1500);

    const result = await page.evaluate(() => {
      return [...document.querySelectorAll('canvas')].map((canvas) => {
        const gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
        const pixels = new Uint8Array(4 * canvas.width * canvas.height);
        gl.readPixels(0, 0, canvas.width, canvas.height, gl.RGBA, gl.UNSIGNED_BYTE, pixels);

        const unique = new Set();
        const stride = 4 * 37;
        for (let i = 0; i < pixels.length; i += stride) {
          unique.add(`${pixels[i]},${pixels[i + 1]},${pixels[i + 2]},${pixels[i + 3]}`);
        }

        return {
          width: canvas.width,
          height: canvas.height,
          uniquePixels: unique.size,
        };
      });
    });

    await page.close();
    results.push({ viewport, canvases: result });
  }

  console.log(JSON.stringify(results));
  await browser.close();

  if (
    results.some(({ canvases }) =>
      canvases.length !== 2 ||
      canvases.some((item) => item.width <= 0 || item.height <= 0 || item.uniquePixels < 2)
    )
  ) {
    process.exit(1);
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
