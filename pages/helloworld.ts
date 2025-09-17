export const onRequestPost = (): Response => {
  return new Response(Json.stringify({ output: "hello world!" })), {
    headers: { "Content-Type": "application/json"}
  });
};
