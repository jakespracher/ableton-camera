type SidecarDialogPayload = {
  sidecarPath?: unknown;
};

export function parseSidecarDialogResult(result: string): string {
  if (!result.trim()) {
    throw new Error("No sidecar path selected.");
  }

  let payload: SidecarDialogPayload;
  try {
    payload = JSON.parse(result) as SidecarDialogPayload;
  } catch {
    throw new Error("Could not parse sidecar dialog result.");
  }

  if (typeof payload.sidecarPath !== "string" || !payload.sidecarPath.trim()) {
    throw new Error("No sidecar path selected.");
  }
  return payload.sidecarPath.trim();
}

export function renderMessageDialog(title: string, message: string): string {
  const safeTitle = escapeHtml(title);
  const safeMessage = escapeHtml(message);
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <style>
      body {
        box-sizing: border-box;
        font-family: system-ui, sans-serif;
        margin: 0;
        padding: 16px;
      }
      h1 {
        font-size: 15px;
        font-weight: 650;
        margin: 0 0 10px;
      }
      p {
        font-size: 13px;
        line-height: 1.35;
        margin: 0 0 16px;
        white-space: pre-wrap;
      }
      button {
        font: inherit;
        padding: 6px 14px;
      }
    </style>
  </head>
  <body>
    <h1>${safeTitle}</h1>
    <p>${safeMessage}</p>
    <button id="close" autofocus>Close</button>
    <script>
      function send(result) {
        const payload = { method: "close_and_send", params: [result] };
        if (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.live) {
          window.webkit.messageHandlers.live.postMessage(payload);
        } else if (window.chrome && window.chrome.webview) {
          window.chrome.webview.postMessage(payload);
        }
      }
      document.getElementById("close").addEventListener("click", function () {
        send("{}");
      });
    </script>
  </body>
</html>`;
}

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
