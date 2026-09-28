// Draw writing space (dot grid, ruled lines, checkbox rows) to fit each box exactly.
(() => {
  const MM = 96 / 25.4;
  const NS = "http://www.w3.org/2000/svg";
  for (const el of document.querySelectorAll(".gen")) {
    const w = el.clientWidth, h = el.clientHeight;
    const p = parseFloat(el.dataset.pitch) * MM;
    const kind = el.dataset.kind;
    const rows = Math.floor(h / p);
    if (rows < 1 || w < 4) continue;
    const parts = [];
    if (kind === "dots") {
      const cols = Math.floor(w / p);
      const ox = (w - (cols - 1) * p) / 2, oy = (h - (rows - 1) * p) / 2;
      // one path of zero-length round-capped segments: tiny, and vector in print
      let d = "";
      for (let r = 0; r < rows; r++)
        for (let c = 0; c < cols; c++) d += `M${(ox + c * p).toFixed(2)} ${(oy + r * p).toFixed(2)}h0`;
      parts.push(`<path d="${d}" class="dotp"/>`);
    } else if (kind === "lines") {
      let d = "";
      for (let r = 1; r <= rows; r++) d += `M0 ${(r * p - 0.5).toFixed(2)}H${w.toFixed(2)}`;
      parts.push(`<path d="${d}" class="rl"/>`);
    } else if (kind === "checks") {
      const box = 2.4 * MM;
      let lines = "", boxes = "";
      for (let r = 0; r < rows; r++) {
        const y = r * p;
        boxes += `<rect x="0.6" y="${(y + (p - box) / 2).toFixed(2)}" width="${box.toFixed(2)}" height="${box.toFixed(2)}" rx="2"/>`;
        lines += `M${(box + 5).toFixed(2)} ${(y + p - 0.5).toFixed(2)}H${w.toFixed(2)}`;
      }
      parts.push(`<path d="${lines}" class="rl"/><g class="cb">${boxes}</g>`);
    }
    el.innerHTML = `<svg xmlns="${NS}" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">${parts.join("")}</svg>`;
  }
})();
