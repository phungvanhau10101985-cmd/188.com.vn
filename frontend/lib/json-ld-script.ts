/** An toàn khi nhúng JSON-LD trong <script>: tránh "</..." trong nội dung làm đóng thẻ sớm → SyntaxError. */
export function serializeJsonLdForScript(data: unknown): string {
  return JSON.stringify(data).replace(/</g, "\\u003c");
}
