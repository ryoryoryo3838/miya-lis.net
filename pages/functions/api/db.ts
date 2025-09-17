
interface Env {
  DB: D1Database;
}

export const onRequestPost: PagesFunction<Env> = async ({ request, env }) => {
  try {
    const { sql } = await request.json();
    
    // プレースホルダー `?` と `.bind()` を使用
    const { success } = await env.DB.prepare(
      sql
    ).run();
