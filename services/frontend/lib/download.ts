// Client-only download helpers. Blob + object URL rather than a raw data:
// URI so PDF-sized payloads don't risk hitting a browser's URL length limit.

function triggerDownload(filename: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function downloadBase64(filename: string, base64: string, mimeType: string) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  triggerDownload(filename, new Blob([bytes], { type: mimeType }));
}

export function downloadText(filename: string, text: string, mimeType = "text/plain") {
  triggerDownload(filename, new Blob([text], { type: mimeType }));
}
