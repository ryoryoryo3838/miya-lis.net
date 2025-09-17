export const onRequestPost = (): Response => {
  return new Response(
    JSON.stringify({ output: "hello world!" }), 
    {
      headers: { "Content-Type": "application/json"}
    }
  );
};
